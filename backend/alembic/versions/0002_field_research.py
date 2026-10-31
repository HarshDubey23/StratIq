"""field research: requests for an industry field researcher and the ground data they collect

Revision ID: 0002_field_research
Revises: 0001_initial
Create Date: 2026-10-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_field_research"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table(
        "field_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("specialty", sa.String(160), nullable=False),
        sa.Column("researcher_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("brief", sa.Text, nullable=False, server_default=""),
        sa.Column("due_date", sa.String(10), nullable=True),
        ts("created_at"), ts("updated_at"),
    )
    op.create_index("ix_field_requests_project_id", "field_requests", ["project_id"])
    op.create_table(
        "field_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(36), sa.ForeignKey("field_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        sa.Column("collected_by", sa.String(120), nullable=False, server_default=""),
        sa.Column("competitor_id", sa.String(36), sa.ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True),
        ts("created_at"),
    )
    op.create_index("ix_field_records_project_id", "field_records", ["project_id"])


def downgrade():
    op.drop_index("ix_field_records_project_id", table_name="field_records")
    op.drop_table("field_records")
    op.drop_index("ix_field_requests_project_id", table_name="field_requests")
    op.drop_table("field_requests")
