"""Initial schema: registered models, inference requests, request metrics, health checks.

Revision ID: 0001
Revises:
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registered_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_identifier", sa.String(length=200), nullable=False),
        sa.Column("endpoint_url", sa.String(length=500), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('demo', 'openai_compatible', 'vllm', 'huggingface')",
            name=op.f("ck_registered_models_provider_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('unknown', 'healthy', 'unhealthy')",
            name=op.f("ck_registered_models_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registered_models")),
        sa.UniqueConstraint("name", name=op.f("uq_registered_models_name")),
    )
    op.create_table(
        "health_checks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('healthy', 'unhealthy')",
            name=op.f("ck_health_checks_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["registered_models.id"],
            name=op.f("fk_health_checks_model_id_registered_models"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_health_checks")),
    )
    op.create_index(
        op.f("ix_health_checks_checked_at"),
        "health_checks",
        ["checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_health_checks_model_id_checked_at",
        "health_checks",
        ["model_id", "checked_at"],
        unique=False,
    )
    op.create_table(
        "inference_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("model_id", sa.Uuid(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("upstream_status_code", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "source IN ('playground', 'api', 'demo_seed')",
            name=op.f("ck_inference_requests_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('success', 'error')",
            name=op.f("ck_inference_requests_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["registered_models.id"],
            name=op.f("fk_inference_requests_model_id_registered_models"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_requests")),
    )
    op.create_index(
        op.f("ix_inference_requests_created_at"),
        "inference_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_inference_requests_is_demo_created_at",
        "inference_requests",
        ["is_demo", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_inference_requests_model_id_created_at",
        "inference_requests",
        ["model_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "request_metrics",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("token_count_source", sa.String(length=16), nullable=True),
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "token_count_source IS NULL OR token_count_source IN ('exact', 'estimated')",
            name=op.f("ck_request_metrics_token_count_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["inference_requests.id"],
            name=op.f("fk_request_metrics_request_id_inference_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_id", name=op.f("pk_request_metrics")),
    )


def downgrade() -> None:
    op.drop_table("request_metrics")
    op.drop_index("ix_inference_requests_model_id_created_at", table_name="inference_requests")
    op.drop_index("ix_inference_requests_is_demo_created_at", table_name="inference_requests")
    op.drop_index(op.f("ix_inference_requests_created_at"), table_name="inference_requests")
    op.drop_table("inference_requests")
    op.drop_index("ix_health_checks_model_id_checked_at", table_name="health_checks")
    op.drop_index(op.f("ix_health_checks_checked_at"), table_name="health_checks")
    op.drop_table("health_checks")
    op.drop_table("registered_models")
