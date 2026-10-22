"""
app/schemas/scoring.py — 记分牌模块 Pydantic Schema

依据：API §5 scoring 端点契约 / 切片 04-scoring/backend.md §4
规范：{Entity}Request / {Entity}Response 命名
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from typing import Literal


# =============================================================================
# 请求 Schema
# =============================================================================

class MatchCreateRequest(BaseModel):
    """创建比赛请求"""

    opponent_name: str = Field(..., min_length=1, max_length=64, description="对手名")
    opponent_rating: Optional[int] = Field(default=None, ge=500, le=3000, description="对手积分")
    format: Literal["bo1", "bo3", "bo5", "bo7", "custom"] = Field(default="bo5", description="赛制")
    match_type: Literal["friendly", "tournament", "training"] = Field(default="friendly", description="比赛类型")
    target_score: int = Field(default=11, ge=1, le=21, description="目标分")


class ScoreRequest(BaseModel):
    """记分请求"""

    scorer: Literal["user", "opponent"] = Field(..., description="得分方")
    score_method: Literal["serve_point", "rally_point", "opponent_error"] = Field(..., description="得分方式")
    technique_action: Optional[str] = Field(default=None, max_length=30, description="技术动作")


class UndoRequest(BaseModel):
    """撤销请求 — 可选携带 expected_seq 做乐观并发控制"""

    expected_seq: Optional[int] = Field(default=None, ge=1, description="期望撤销的序号")


# =============================================================================
# 响应 Schema
# =============================================================================

class MatchBrief(BaseModel):
    """比赛简要信息"""

    id: int
    opponent_name: Optional[str] = None
    format: str
    match_type: str
    status: str
    current_score_user: int
    current_score_opp: int
    is_win: Optional[bool] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoreRecordBrief(BaseModel):
    """得分记录简要"""

    seq: int
    scorer: str
    score_method: Optional[str] = None
    technique_action: Optional[str] = None
    game_number: int

    model_config = {"from_attributes": True}


class MatchDetail(BaseModel):
    """比赛详情"""

    id: int
    opponent_name: Optional[str] = None
    opponent_rating: Optional[int] = None
    format: str
    match_type: str
    target_score: int
    status: str
    current_score_user: int
    current_score_opp: int
    current_server: Optional[str] = None
    current_game: int
    is_win: Optional[bool] = None
    final_score: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MatchDetailWithSequence(MatchDetail):
    """比赛详情（含比分序列）"""

    score_sequence: list[ScoreRecordBrief] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    """记分响应"""

    sequence: int
    score: str  # "u:o"
    current_server: str
    game_number: int
    is_key_point: bool
    match_status: str
    should_change_sides: bool = False


class UndoResponse(BaseModel):
    """撤销响应"""

    sequence: int
    score: str
    type: str = "undo"


class FinishResponse(BaseModel):
    """结束比赛响应"""

    match_id: int
    final_score: str
    is_win: bool
    statistic_id: int


class MatchStartResponse(BaseModel):
    """开始比赛响应"""

    match_id: int
    status: str = "in_progress"
    started_at: str


class MatchAbandonResponse(BaseModel):
    """放弃比赛响应"""

    match_id: int
    status: str = "abandoned"
    abandoned_at: str


class MatchResumeResponse(BaseModel):
    """恢复比赛响应"""

    match_id: int
    status: str = "in_progress"
    resumed_at: str


class MatchStatisticResponse(BaseModel):
    """比赛统计响应"""

    match_id: int
    stats_data: dict
