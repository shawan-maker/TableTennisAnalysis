"""s2_scoring_match_data_tables

Revision ID: 51586e688365
Revises: 44981acca4fa
Create Date: 2026-10-22 05:51:27.177293+00:00

S2 新增表：match, score_record, match_statistic, match_record,
manual_score_detail, share_record, notification_record

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '51586e688365'
down_revision: Union[str, None] = '44981acca4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # match — 比赛主表（状态机）
    op.create_table('match',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('opponent_name', sa.String(length=64), nullable=True),
        sa.Column('opponent_rating', sa.Integer(), nullable=True),
        sa.Column('format', sa.String(length=20), nullable=False, server_default='bo5'),
        sa.Column('match_type', sa.String(length=20), nullable=False, server_default='friendly'),
        sa.Column('target_score', sa.Integer(), nullable=False, server_default='11'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='setup'),
        sa.Column('current_score_user', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_score_opp', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_server', sa.String(length=10), nullable=True),
        sa.Column('current_game', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_win', sa.Boolean(), nullable=True),
        sa.Column('final_score', sa.String(length=20), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('abandoned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('score_sequence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_match_status', 'match', ['status'], unique=False)
    op.create_index('idx_match_user_created', 'match', ['user_id', 'created_at'], unique=False)

    # score_record — 得分记录（Redis INCR 序号）
    op.create_table('score_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('scorer', sa.String(length=10), nullable=False),
        sa.Column('score_method', sa.String(length=32), nullable=True),
        sa.Column('technique_action', sa.String(length=32), nullable=True),
        sa.Column('game_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_key_point', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['match.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_score_record_match_seq', 'score_record', ['match_id', 'sequence'], unique=False)
    op.create_index('idx_score_record_match_game', 'score_record', ['match_id', 'game_number'], unique=False)

    # match_statistic — 比赛统计（一对一）
    op.create_table('match_statistic',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('stats_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['match.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id')
    )

    # match_record — 比赛记录（手动录入 + 记分牌关联）
    op.create_table('match_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('match_id', sa.BigInteger(), nullable=True),
        sa.Column('opponent_name', sa.String(length=64), nullable=True),
        sa.Column('opponent_rating', sa.Integer(), nullable=True),
        sa.Column('my_score', sa.Integer(), nullable=False),
        sa.Column('opponent_score', sa.Integer(), nullable=False),
        sa.Column('is_win', sa.Boolean(), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False, server_default='bo5'),
        sa.Column('match_type', sa.String(length=20), nullable=False, server_default='friendly'),
        sa.Column('match_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_detailed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['match.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_mrecord_user_date', 'match_record', ['user_id', 'match_date'], unique=False)

    # manual_score_detail — 手动得分明细
    op.create_table('manual_score_detail',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('match_record_id', sa.BigInteger(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('scorer', sa.String(length=10), nullable=False),
        sa.Column('score_method', sa.String(length=32), nullable=True),
        sa.Column('technique_action', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['match_record_id'], ['match_record.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_msd_record_seq', 'manual_score_detail', ['match_record_id', 'sequence'], unique=False)

    # share_record — 分享报告（report_id FK 在 S3 添加）
    op.create_table('share_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('report_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('share_token', sa.String(length=64), nullable=False),
        sa.Column('share_scope', sa.String(length=20), nullable=False, server_default='public'),
        sa.Column('card_image_url', sa.String(length=512), nullable=True),
        sa.Column('expire_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_token')
    )
    op.create_index('idx_share_user_created', 'share_record', ['user_id', 'created_at'], unique=False)

    # notification_record — 通知记录（S2 仅建表）
    op.create_table('notification_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_notif_user_read_created', 'notification_record', ['user_id', 'is_read', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_notif_user_read_created', table_name='notification_record')
    op.drop_table('notification_record')
    op.drop_index('idx_share_user_created', table_name='share_record')
    op.drop_table('share_record')
    op.drop_index('idx_msd_record_seq', table_name='manual_score_detail')
    op.drop_table('manual_score_detail')
    op.drop_index('idx_mrecord_user_date', table_name='match_record')
    op.drop_table('match_record')
    op.drop_table('match_statistic')
    op.drop_index('idx_score_record_match_seq', table_name='score_record')
    op.drop_index('idx_score_record_match_game', table_name='score_record')
    op.drop_table('score_record')
    op.drop_index('idx_match_user_created', table_name='match')
    op.drop_index('idx_match_status', table_name='match')
    op.drop_table('match')
