"""
app/models/match.py — Match + ScoreRecord + MatchStatistic + MatchRecord + ManualScoreDetail + ShareRecord

依据：DB §2.10 match / §2.11 score_record / §2.12 match_statistic / §2.13 match_record
      §2.14 manual_score_detail / §2.9 share_record
      切片 04-scoring/backend.md §3 + 05-match_data/backend.md §3
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Match(Base):
    """
    比赛主表 — 记分牌状态机。
    DB 设计 §2.10 / v1.6
    状态机：setup -> in_progress -> finished / abandoned
    """

    __tablename__ = "match"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    opponent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opponent_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str] = mapped_column(String(20), default="bo5", nullable=False)  # bo1/bo3/bo5/bo7/custom
    match_type: Mapped[str] = mapped_column(String(20), default="friendly", nullable=False)  # friendly/tournament/training
    target_score: Mapped[int] = mapped_column(Integer, default=11, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="setup", nullable=False)  # setup/in_progress/finished/abandoned
    current_score_user: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_score_opp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_server: Mapped[str | None] = mapped_column(String(10), nullable=True)  # user/opponent
    current_game: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_win: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score_sequence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Redis mirror
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- 关系 ---
    score_records: Mapped[list["ScoreRecord"]] = relationship(
        back_populates="match", cascade="all, delete-orphan",
        order_by="ScoreRecord.sequence",
    )
    statistic: Mapped["MatchStatistic | None"] = relationship(
        back_populates="match", cascade="all, delete-orphan", uselist=False,
    )

    __table_args__ = (
        Index("idx_match_user_created", "user_id", "created_at"),
        Index("idx_match_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Match(id={self.id}, status={self.status!r}, score={self.current_score_user}:{self.current_score_opp})>"


class ScoreRecord(Base):
    """得分记录 — Redis INCR 全局序号。DB §2.11"""

    __tablename__ = "score_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("match.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # Redis INCR
    scorer: Mapped[str] = mapped_column(String(10), nullable=False)  # user/opponent
    score_method: Mapped[str | None] = mapped_column(String(32), nullable=True)  # serve_point/rally_point/opponent_error
    technique_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    game_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_key_point: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- 关系 ---
    match: Mapped["Match"] = relationship(back_populates="score_records")

    __table_args__ = (
        Index("idx_score_record_match_seq", "match_id", "sequence"),
        Index("idx_score_record_match_game", "match_id", "game_number"),
    )

    def __repr__(self) -> str:
        return f"<ScoreRecord(id={self.id}, match_id={self.match_id}, seq={self.sequence}, scorer={self.scorer!r})>"


class MatchStatistic(Base):
    """比赛统计 — 一对一。DB §2.12"""

    __tablename__ = "match_statistic"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("match.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stats_data: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {score_distribution, key_points, technique_breakdown, total_points}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- 关系 ---
    match: Mapped["Match"] = relationship(back_populates="statistic")

    def __repr__(self) -> str:
        return f"<MatchStatistic(id={self.id}, match_id={self.match_id})>"


class MatchRecord(Base):
    """比赛记录 — 手动录入 + 记分牌关联。DB §2.13"""

    __tablename__ = "match_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    match_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("match.id", ondelete="SET NULL"), nullable=True
    )
    opponent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opponent_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    my_score: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    is_win: Mapped[bool] = mapped_column(Boolean, nullable=False)
    format: Mapped[str] = mapped_column(String(20), default="bo5", nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="friendly", nullable=False)
    match_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_detailed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- 关系 ---
    details: Mapped[list["ManualScoreDetail"]] = relationship(
        back_populates="record", cascade="all, delete-orphan",
        order_by="ManualScoreDetail.sequence",
    )

    __table_args__ = (
        Index("idx_mrecord_user_date", "user_id", "match_date"),
    )

    def __repr__(self) -> str:
        return f"<MatchRecord(id={self.id}, user_id={self.user_id}, score={self.my_score}:{self.opponent_score})>"


class ManualScoreDetail(Base):
    """手动记分详情 — 一对多关联 MatchRecord。DB §2.14"""

    __tablename__ = "manual_score_detail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("match_record.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    scorer: Mapped[str] = mapped_column(String(10), nullable=False)  # user/opponent
    score_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    technique_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # --- 关系 ---
    record: Mapped["MatchRecord"] = relationship(back_populates="details")

    __table_args__ = (
        Index("idx_msd_record_seq", "match_record_id", "sequence"),
    )

    def __repr__(self) -> str:
        return f"<ManualScoreDetail(id={self.id}, seq={self.sequence}, scorer={self.scorer!r})>"


class ShareRecord(Base):
    """
    分享报告 — 7 天有效 Token。
    DB §2.9 — report_id FK 指向 analysis_report（S3 创建），S2 阶段先建表不设 FK 约束。
    S3 创建 analysis_report 表后通过 Alembic 迁移补充 FK。
    """

    __tablename__ = "share_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # S2 阶段: report_id 不设 FK（analysis_report 表 S3 才创建）
    report_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    share_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    share_scope: Mapped[str] = mapped_column(String(20), default="public", nullable=False)  # public/friend
    card_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_share_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ShareRecord(id={self.id}, token={self.share_token[:8]}...)>"
