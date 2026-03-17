from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_client_saved_masters"
down_revision = "0002_add_availability_slots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_saved_masters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.UniqueConstraint("tg_user_id", "master_id", name="uq_client_saved_master"),
    )


def downgrade() -> None:
    op.drop_table("client_saved_masters")
