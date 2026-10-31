"""Real-data layer: HCES curves, RWI rank matching, data-driven segments/WTP/participation, road distances."""
import numpy as np
import pytest

from app.categories.archetypes import get_archetype
from app.engine import model as em
from app.engine.abm import run_abm
from app.engine.economics import behaviour as eb
from app.engine.economics import income as ei
from app.engine.simulate import simulate
from app.providers import routing as rt


def test_hces_curves_reproduce_published_points():
    h = ei.hces()
    for sector in ("rural", "urban"):
        c = ei.curve(sector)
        assert c.fit_error < 0.07  # Singh-Maddala within 7% of every published quantile and class mean
        p50 = h["national_fractiles"][sector]["upper"][5]
        assert abs(c.median / p50 - 1) < 0.03
    for state, d in h["state_deciles"]["rural"].items():
        assert abs(ei.curve("rural", state).median / d[4] - 1) < 0.03, state


def test_rank_matching_preserves_national_distribution():
    """Uniform tile percentiles + any loading a => draws follow the official national curve."""
    nat = ei.national()
    pct = (np.arange(500) + 0.5) / 500
    ctx = ei.IncomeContext("rwi_rank", pct, None, "urban", 0.6, [], "x", 0.0)
    x, u = ctx.draw(np.random.default_rng(0), np.repeat(np.arange(500), 80))
    for q in (0.1, 0.5, 0.9):
        assert abs(np.quantile(x, q) / nat.ppf(q) - 1) < 0.03
    assert abs(u.mean() - 0.5) < 0.01


def test_poor_and_rich_places_get_different_income_mix_and_wtp(monkeypatch):
    monkeypatch.setattr(ei, "_grid", lambda: None)  # state-curve path, independent of the shipped wealth grid
    arch = get_archetype("membership")
    poor = ei.build_context([25.6], [85.1], state="Bihar", sector="rural")
    rich = ei.build_context([10.0], [76.3], state="Kerala", sector="urban")
    assert poor.method == rich.method == "state_curve"
    bp, br = eb.build(arch, "gym", poor, 3), eb.build(arch, "gym", rich, 3)
    assert bp.summary["classes"][0]["share"] > 0.5 > br.summary["classes"][0]["share"]
    assert br.summary["median_mpce"] > 1.5 * bp.summary["median_mpce"]
    # gym penetration is anchored to 0.8% nationally and scaled by the local income mix
    assert bp.params["participation"][0] < 0.008 < br.params["participation"][0]
    assert bp.params["participation"][3] == "industry"
    assert all(s.wtp_multiplier < t.wtp_multiplier for s, t in zip(bp.segments[:1], bp.segments[1:]))


def test_routing_matrix_falls_back_per_column():
    zones = np.array([[28.60, 77.20], [28.61, 77.21]])
    routing = {"dest_keys": [rt.point_key(28.6, 77.2)], "car": {"km": [[1.2], [None]], "min": [[3.0], [None]]}}
    km, mins, share = rt.matrix_for(routing, routing["dest_keys"], [(rt.point_key(28.6, 77.2), 28.6, 77.2), ("x", 28.62, 77.22)],
                                    zones, 1.3, 20.0)
    assert km[0, 0] == pytest.approx(1.2) and share == pytest.approx(0.25)
    assert np.isfinite(mins).all() and km[1, 0] > 0  # unrouted cell -> straight line x circuity


def test_state_names_normalise_to_hces():
    assert ei.normalise_state("Orissa") == "Odisha"
    assert ei.normalise_state("uttar pradesh") == "Uttar Pradesh"
    assert ei.normalise_state("Mahārāshtra") == "Maharashtra" and ei.normalise_state("Tamil Nādu") == "Tamil Nadu"
    assert ei.normalise_state(None) is None


def test_end_to_end_with_evidence():
    arch = get_archetype("membership")
    zones = [em.Zone(25.60 + 0.004 * i, 85.10 + 0.004 * j, 900.0) for i in range(4) for j in range(4)]
    comps = [em.Competitor("c1", "Rival", 25.61, 85.11)]
    biz = em.BusinessInputs(25.605, 85.105, price=1500, rent=40000, payroll=60000)
    ctx = ei.build_context([z.lat for z in zones], [z.lng for z in zones], state="Bihar", sector="urban")
    beh = eb.build(arch, "gym", ctx, len(zones))
    arch2 = eb.apply(arch, beh)
    res = simulate(arch2, zones, comps, biz, {}, mc_draws=40, seed=1, evidence=beh.params, seg_share_z=beh.zone_shares,
                   with_sensitivity=False)
    assert res["summary"]
    params = em.ResolvedParams.from_archetype(arch2, {}, beh.params)
    assert params.status["participation"] == "industry" and params.status["wtp_sigma"] == "derived"
    out = run_abm(arch2, zones, comps, biz, params, 1500.0, n_agents=600, days=14, seed=3, income=ctx, behaviour=beh)
    cols = out["agents"]["columns"]
    mp = [r[cols.index("mpce")] for r in out["agents"]["rows"]]
    assert all(v and v > 0 for v in mp)
    # richer agents value the gym more
    wtp = np.array([r[cols.index("wtp")] for r in out["agents"]["rows"]], float)
    assert np.corrcoef(np.log(mp), np.log(wtp))[0, 1] > 0.5
