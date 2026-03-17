from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_availability_slots"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "availability_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("slot_time", sa.Time(), nullable=False),
        sa.UniqueConstraint(
            "master_id", "slot_date", "slot_time", name="uq_availability_slot"
        ),
    )


def downgrade() -> None:
    op.drop_table("availability_slots")
