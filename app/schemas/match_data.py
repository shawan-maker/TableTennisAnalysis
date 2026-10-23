"""
app/schemas/match_data.py — 比赛数据模块 Pydantic Schema

依据：API §7 match-data 端点契约 / 切片 05-match_data/backend.md §4
规范：{Entity}Request / {Entity}Response 命名
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from typing import Literal


# =============================================================================
# 请求 Schema
# =============================================================================

class ManualScoreDetailItem(BaseModel):
    """手动得分明细项"""

    sequence: int = Field(..., ge=1, description="得分序号")
    scorer: Literal["user", "opponent"] = Field(..., description="得分方")
    score_method: Literal["serve_point", "rally_point", "opponent_error"] = Field(..., description="得分方式")
    technique_action: Optional[str] = Field(default=None, max_length=30, description="技术动作")


class MatchRecordCreateRequest(BaseModel):
    """创建比赛记录请求（快速/详细录入）"""

    opponent_name: str = Field(..., min_length=1, max_length=64, description="对手名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    my_score: int = Field(..., ge=0, le=99, description="我的得分")
    opponent_score: int = Field(..., ge=0, le=99, description="对手得分")
    format: Literal["bo1", "bo3", "bo5", "bo7", "custom"] = Field(default="bo5", description="赛制")
    match_type: Literal["friendly", "tournament", "training"] = Field(default="friendly", description="比赛类型")
    match_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="比赛日期")
    details: Optional[list[ManualScoreDetailItem]] = Field(default=None, description="详细得分明细")
    match_id: Optional[int] = Field(default=None, ge=1, description="关联记分牌比赛 ID")

    @model_validator(mode="after")
    def validate_score(self):
        """比分不能相同 + 日期不能晚于当前时间"""
        if self.my_score == self.opponent_score:
            raise ValueError("比分不能相同")
        if self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self


class MatchRecordUpdate(BaseModel):
    """编辑比赛记录请求（PATCH 语义）"""

    opponent_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000)
    my_score: Optional[int] = Field(default=None, ge=0, le=99)
    opponent_score: Optional[int] = Field(default=None, ge=0, le=99)
    match_date: Optional[datetime] = Field(default=None)
    match_type: Optional[Literal["friendly", "tournament", "training"]] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_score_update(self):
        """比分不能相同（仅当两个分数同时传入时检查）"""
        if self.my_score is not None and self.opponent_score is not None:
            if self.my_score == self.opponent_score:
                raise ValueError("比分不能相同")
        if self.match_date is not None and self.match_date > datetime.now(timezone.utc):
            raise ValueError("比赛日期不能晚于当前时间")
        return self


class MatchRecordListQuery(BaseModel):
    """比赛记录列表查询"""

    result: Optional[Literal["win", "lose", "all"]] = Field(default="all")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# =============================================================================
# 响应 Schema
# =============================================================================

class MatchRecordBrief(BaseModel):
    """比赛记录简要"""

    id: int
    opponent_name: Optional[str] = None
    opponent_rating: Optional[int] = None
    my_score: int
    opponent_score: int
    is_win: bool
    format: str
    match_type: str
    match_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MatchRecordDetail(MatchRecordBrief):
    """比赛记录详情（含得分明细）"""

    match_id: Optional[int] = None
    is_detailed: bool = False
    notes: Optional[str] = None
    details: list[ManualScoreDetailItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MatchRecordCreateResponse(BaseModel):
    """创建比赛记录响应"""

    id: int
    is_win: bool
