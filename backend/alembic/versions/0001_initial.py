"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("preferences", JSONB, nullable=False, server_default="{}"),
        ts("created_at"), ts("updated_at"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("objective", sa.String(40), nullable=False),
        sa.Column("decision_goal", sa.String(20), nullable=False, server_default="profit"),
        sa.Column("category", JSONB, nullable=False),
        sa.Column("profile", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default=sa.false()),
        ts("created_at"), ts("updated_at"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "candidate_locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("address", sa.Text, nullable=False, server_default=""),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("geog", Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("catchment", JSONB, nullable=False),
        sa.Column("manual_population", sa.Float, nullable=True),
        ts("created_at"), ts("updated_at"),
    )
    op.create_index("ix_candidate_locations_project_id", "candidate_locations", ["project_id"])
    op.create_index("ix_candidate_locations_geog", "candidate_locations", ["geog"], postgresql_using="gist")

    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("candidate_locations.id", ondelete="CASCADE"), nullable=False),
        ts("retrieved_at"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("catchment_geojson", JSONB, nullable=False),
        sa.Column("catchment_method", sa.String(20), nullable=False),
        sa.Column("zones", JSONB, nullable=False),
        sa.Column("population", JSONB, nullable=False),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("coverage", JSONB, nullable=False),
        sa.Column("activity_points", JSONB, nullable=False, server_default="[]"),
        sa.Column("errors", JSONB, nullable=False, server_default="[]"),
    )
    op.create_index("ix_market_snapshots_project_id", "market_snapshots", ["project_id"])
    op.create_index("ix_market_snapshots_location_id", "market_snapshots", ["location_id"])

    op.create_table(
        "competitors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(80), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("geog", Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("tags", JSONB, nullable=False, server_default="{}"),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("price_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("quality", sa.Float, nullable=True),
        sa.Column("quality_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("is_hypothetical", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        ts("created_at"), ts("updated_at"),
        sa.UniqueConstraint("project_id", "source", "source_ref", name="uq_competitor_source_ref"),
    )
    op.create_index("ix_competitors_project_id", "competitors", ["project_id"])
    op.create_index("ix_competitors_geog", "competitors", ["geog"], postgresql_using="gist")

    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("candidate_locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_baseline", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("inputs", JSONB, nullable=False),
        ts("created_at"), ts("updated_at"),
    )
    op.create_index("ix_scenarios_project_id", "scenarios", ["project_id"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("market_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("inputs_snapshot", JSONB, nullable=False),
        sa.Column("seed", sa.Integer, nullable=False),
        ts("started_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("results", JSONB, nullable=True),
    )
    op.create_index("ix_simulation_runs_project_id", "simulation_runs", ["project_id"])
    op.create_index("ix_simulation_runs_scenario_id", "simulation_runs", ["scenario_id"])

    op.create_table(
        "actual_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("units", sa.Float, nullable=True),
        sa.Column("revenue", sa.Float, nullable=True),
        sa.Column("costs", sa.Float, nullable=True),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        ts("created_at"), ts("updated_at"),
        sa.UniqueConstraint("project_id", "period", name="uq_outcome_period"),
    )
    op.create_index("ix_actual_outcomes_project_id", "actual_outcomes", ["project_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        ts("created_at"),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column("content", JSONB, nullable=False),
    )
    op.create_index("ix_reports_project_id", "reports", ["project_id"])

    op.create_table(
        "provider_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        ts("fetched_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_provider_cache_expires_at", "provider_cache", ["expires_at"])


def downgrade():
    for t in ("provider_cache", "reports", "actual_outcomes", "simulation_runs", "scenarios", "competitors",
              "market_snapshots", "candidate_locations", "projects", "users"):
        op.drop_table(t)
