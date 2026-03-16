from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("language_code", sa.String(), nullable=True),
        sa.Column("is_master", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "master_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "working_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
    )

    op.create_table(
        "daily_booking_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("max_bookings", sa.Integer(), nullable=False),
        sa.UniqueConstraint("master_id", "weekday", name="uq_daily_limit_master_day"),
    )

    op.create_table(
        "client_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id", sa.Integer(), sa.ForeignKey("master_profiles.id"), nullable=False
        ),
        sa.Column(
            "client_id", sa.Integer(), sa.ForeignKey("client_profiles.id"), nullable=False
        ),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="CONFIRMED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "master_id",
            "client_id",
            "service_id",
            "start_at",
            name="uq_booking_idempotent",
        ),
    )


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("client_profiles")
    op.drop_table("daily_booking_limits")
    op.drop_table("working_windows")
    op.drop_table("services")
    op.drop_table("master_profiles")
    op.drop_table("users")

