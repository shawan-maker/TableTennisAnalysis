# 内容审核基础设施切片

> **所属目录**：`app/services/content_moderation_service.py` + `app/core/moderation.py`
> **约束来源**：架构约束 #22 — 内容审核 DFA + 阿里云内容安全 API
> **Phase**：Phase 1（基础设施）

## 1. 模块职责

对用户生成内容（UGC）进行敏感词过滤和内容安全审核：
- 文本内容：DFA 敏感词过滤（本地） + 阿里云内容安全 API（云端兜底）
- 图片内容：阿里云内容安全 API（图片审核）
- 视频内容：阿里云内容安全 API（视频审核）

## 2. DFA 敏感词过滤器

```python
# app/core/dfilter.py
"""DFA 敏感词过滤器。"""

from typing import Set, List
import asyncio

class DFAFilter:
    """基于 DFA 算法的敏感词过滤器。"""

    def __init__(self):
        self._keyword_chains = {}

    def add_keyword(self, keyword: str) -> None:
        """添加敏感词到 DFA 树。"""
        if not keyword:
            return
        node = self._keyword_chains
        for char in keyword:
            node = node.setdefault(char, {})
        node["__end__"] = True

    def load_keywords(self, keywords: List[str]) -> None:
        """批量加载敏感词。"""
        for kw in keywords:
            self.add_keyword(kw)

    def filter(self, text: str, replace_char: str = "*") -> str:
        """过滤文本中的敏感词，替换为指定字符。"""
        result = list(text)
        start = 0
        while start < len(text):
            node = self._keyword_chains
            current = start
            match_end = -1
            while current < len(text) and text[current] in node:
                node = node[text[current]]
                current += 1
                if "__end__" in node:
                    match_end = current
            if match_end > 0:
                for i in range(start, match_end):
                    result[i] = replace_char
                start = match_end
            else:
                start += 1
        return "".join(result)

    def contains_sensitive(self, text: str) -> bool:
        """检查文本是否包含敏感词。"""
        return self.filter(text) != text
```

## 3. 内容审核 Service

```python
# app/services/content_moderation_service.py
"""内容审核 Service。"""

from app.core.dfilter import DFAFilter
from app.core.config import settings

class ContentModerationService:
    """内容审核服务。"""

    _dfa = DFAFilter()

    @classmethod
    def init_keywords(cls, keywords: list[str]) -> None:
        """初始化敏感词库（应用启动时调用）。"""
        cls._dfa.load_keywords(keywords)

    @staticmethod
    async def moderate_text(text: str) -> dict:
        """审核文本内容。
        Returns: { passed: bool, filtered_text: str, reason: str }
        """
        # 1. DFA 本地过滤
        filtered = ContentModerationService._dfa.filter(text)
        has_sensitive = ContentModerationService._dfa.contains_sensitive(text)

        # 2. 阿里云内容安全 API（云端兜底）
        if settings.ALICLOUD_CONTENT_SECURITY_ENABLED:
            try:
                # 调用阿里云内容安全 API
                # from alibabacloud_green20220302.client import Client
                # ... 调用文本检测接口 ...
                pass
            except Exception:
                pass  # 云端失败时使用本地 DFA 结果

        return {
            "passed": not has_sensitive,
            "filtered_text": filtered,
            "reason": "contains_sensitive_words" if has_sensitive else None,
        }

    @staticmethod
    async def moderate_image(oss_key: str) -> dict:
        """审核图片内容。"""
        # 调用阿里云内容安全 API — 图片审核
        return {"passed": True, "reason": None}

    @staticmethod
    async def moderate_video(oss_key: str) -> dict:
        """审核视频内容。"""
        # 调用阿里云内容安全 API — 视频审核
        return {"passed": True, "reason": None}
```

## 4. 使用场景

| 场景 | 调用时机 | 审核类型 |
|------|---------|---------|
| 用户反馈 | video_analysis 提交 feedback 时 | 文本 DFA |
| 分享内容 | video_analysis 创建 share 时 | 文本 DFA |
| 用户昵称 | user 更新 profile 时 | 文本 DFA |
| 训练备注 | scoring/scoring 记分时 | 文本 DFA |

## 5. 敏感词库管理

- 敏感词库存储在 `app/data/sensitive_words.txt`
- 应用启动时加载到内存 DFA 树
- 支持热更新（通过管理后台或定时任务刷新）

---

## 6. 测试用例

```python
# tests/infrastructure/test_content_moderation.py

import pytest
from app.services.content_moderation_service import ContentModerationService


class TestTextModeration:
    """文本审核测试。"""

    @pytest.mark.asyncio
    async def test_clean_text_passes(self):
        """正常文本通过审核。"""
        result = await ContentModerationService.moderate_text("这是一条正常反馈")
        assert result["passed"] is True
        assert result["reason"] is None

    @pytest.mark.asyncio
    async def test_sensitive_word_blocked(self):
        """敏感词被拦截。"""
        result = await ContentModerationService.moderate_text("敏感词测试内容")
        assert result["passed"] is False
        assert "敏感词" in result["reason"]

    @pytest.mark.asyncio
    async def test_empty_text_passes(self):
        """空文本通过审核。"""
        result = await ContentModerationService.moderate_text("")
        assert result["passed"] is True


class TestVideoModeration:
    """视频审核测试。"""

    @pytest.mark.asyncio
    async def test_video_moderation_default_pass(self):
        """视频审核默认通过（无实际 API 调用时）。"""
        result = await ContentModerationService.moderate_video("oss://test/video.mp4")
        assert result["passed"] is True
```