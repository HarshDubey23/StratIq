"""Unit tests for background snapshot recovery and resilience in app.services.runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models import MarketSnapshot
from app.services.runs import LOADING_STALE_AFTER, recover_stale_loading_snapshots


def test_recover_stale_loading_snapshots_marks_failed():
    """Verify stale loading snapshots (>5 mins) are marked failed and committed."""
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(minutes=10)

    stale_snap = MarketSnapshot(
        id="snap-1",
        project_id="proj-1",
        location_id="loc-1",
        status="loading",
        retrieved_at=stale_time,
        catchment_geojson={},
        catchment_method="radius",
        zones=[],
        population={},
        sources=[],
        coverage={},
        activity_points=[],
        errors=[],
    )

    mock_db = MagicMock()
    mock_db.scalars.return_value = [stale_snap]

    recovered_count = recover_stale_loading_snapshots(mock_db, max_age=LOADING_STALE_AFTER)

    assert recovered_count == 1
    assert stale_snap.status == "failed"
    assert len(stale_snap.errors) == 1
    assert "interrupted" in stale_snap.errors[0]["message"]
    assert stale_snap.retrieved_at > stale_time
    mock_db.commit.assert_called_once()


def test_recover_stale_loading_snapshots_leaves_fresh_untouched():
    """Verify fresh loading snapshots (<5 mins) are not touched."""
    mock_db = MagicMock()
    mock_db.scalars.return_value = []

    recovered_count = recover_stale_loading_snapshots(mock_db, max_age=LOADING_STALE_AFTER)

    assert recovered_count == 0
    mock_db.commit.assert_not_called()
