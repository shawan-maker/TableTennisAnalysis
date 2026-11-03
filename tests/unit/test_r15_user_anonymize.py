"""
tests/unit/test_r15_user_anonymize.py — R15-User-N1 锁定测试

R15-A5 发现：process_account_deletions 匿名化仅清 4 基础字段
（nickname/avatar_url/phone/openid），User 模型 5 个画像字段
永久留存 → PIPL 删除权不完整：
  * kqs_username：外部平台（开球网）账号名 — 可识别 PII
  * kqs_rating：外部平台关联数据
  * playing_style / self_assessed_level：打法与自评偏好 PII
  * equipment_config：器材配置 JSONB（底板/胶皮等偏好）

R15 修复（app/tasks/user.py 匿名化块）：五字段全部置 None。

锁定矩阵：
  a) 画像字段齐备的到期用户 → 七字段（4 基础 + 5 画像）全部清空
  b) 既有级联语义不回归（status=deleted + 冷静期内对照用户不处理）
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.user import User


class TestR15UserAnonymize:
    """R15-User-N1: 注销匿名化画像字段补齐"""

    async def test_a_profile_fields_anonymized(self, db_session):
        """a) 5 画像字段 + 4 基础字段全部匿名化（到期 73h 用户）"""
        now = datetime.now(timezone.utc)
        victim = User(
            openid="r15_del_openid",
            phone="13800007777",
            nickname="画像齐备用户",
            avatar_url="https://example.com/r15.png",
            status="pending_deletion",
            deletion_reason="不再使用",
            scheduled_deletion_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=73),  # INSERT 显式赋值越过 cutoff
            # R15-User-N1: 画像字段齐备（修复前将永久留存）
            kqs_rating=1850,
            kqs_username="r15_kqs_name",
            playing_style="两面弧圈",
            equipment_config={"blade": "VIS", "forehand": "狂飙3", "backhand": "D05"},
            self_assessed_level="业余高级",
        )
        db_session.add(victim)
        await db_session.commit()
        await db_session.refresh(victim)
        victim_id = victim.id

        from app.tasks.user import process_account_deletions

        result = process_account_deletions.delay()
        assert result.get() == {"status": "ok"}

        async with async_session_factory() as v:
            u = (await v.execute(select(User).where(User.id == victim_id))).scalar_one()
            # 4 基础字段（R14-User-1 既有语义不回归）
            assert u.status == "deleted"
            assert u.nickname == "已注销用户"
            assert u.avatar_url is None
            assert u.phone is None
            assert u.openid is None
            # R15-User-N1: 5 画像字段全部清空
            assert u.kqs_rating is None
            assert u.kqs_username is None
            assert u.playing_style is None
            assert u.equipment_config is None
            assert u.self_assessed_level is None

    async def test_b_fresh_user_untouched(self, db_session):
        """b) 冷静期内用户画像字段不受影响（任务窗口过滤不回归）"""
        fresh = User(
            openid="r15_del_fresh",
            phone="13800006666",
            nickname="冷静期内",
            status="pending_deletion",  # updated_at = 当前 → 未满 72h
            kqs_username="r15_fresh_kqs",
            playing_style="削球",
        )
        db_session.add(fresh)
        await db_session.commit()
        await db_session.refresh(fresh)
        fresh_id = fresh.id

        from app.tasks.user import process_account_deletions

        result = process_account_deletions.delay()
        assert result.get() == {"status": "ok"}

        async with async_session_factory() as v:
            u = (await v.execute(select(User).where(User.id == fresh_id))).scalar_one()
            assert u.status == "pending_deletion"
            assert u.kqs_username == "r15_fresh_kqs"
            assert u.playing_style == "削球"
