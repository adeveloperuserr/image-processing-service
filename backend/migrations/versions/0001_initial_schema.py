"""Initial image, account, and durable job tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Uuid

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "images",
        sa.Column("id", Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("original_path", sa.String(length=600), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("original_path", name="uq_images_original_path"),
    )
    op.create_index("ix_images_user_id", "images", ["user_id"], unique=False)
    op.create_index("ix_images_created_at", "images", ["created_at"], unique=False)

    op.create_table(
        "processing_jobs",
        sa.Column("id", Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("image_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("operations_json", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("output_path", sa.String(length=600), nullable=True),
        sa.Column("output_content_type", sa.String(length=80), nullable=True),
        sa.Column("output_size_bytes", sa.Integer(), nullable=True),
        sa.Column("output_width", sa.Integer(), nullable=True),
        sa.Column("output_height", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_job_user_idempotency"),
    )
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"], unique=False)
    op.create_index("ix_processing_jobs_image_id", "processing_jobs", ["image_id"], unique=False)
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"], unique=False)
    op.create_index(
        "ix_processing_jobs_available_at", "processing_jobs", ["available_at"], unique=False
    )
    op.create_index(
        "ix_processing_jobs_created_at", "processing_jobs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_job_claim", "processing_jobs", ["status", "available_at", "created_at"], unique=False
    )
    op.create_index("ix_job_lease", "processing_jobs", ["status", "lease_until"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_lease", table_name="processing_jobs")
    op.drop_index("ix_job_claim", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_created_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_available_at", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_image_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_user_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_images_created_at", table_name="images")
    op.drop_index("ix_images_user_id", table_name="images")
    op.drop_table("images")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
