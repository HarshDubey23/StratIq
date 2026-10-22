"""Agent Genome: size, consumption audit, conditioning, determinism, and that parameters actually move choices."""
import numpy as np

from app.categories.archetypes import ARCHETYPES
from app.engine import genome as gm
from app.engine.abm import build_population, run_abm
from app.engine.model import BusinessInputs, Competitor, ResolvedParams, Zone

LAT, LNG = 28.67, 77.45


def zones(n=12, pop=1500.0):
    xs = np.linspace(-0.02, 0.02, n)
    return [Zone(LAT + a, LNG + b, pop, 2.0) for a in xs for b in xs]


def comps(k=5):
    r = np.random.default_rng(3)
    return [Competitor(f"c{i}", f"Comp {i}", LAT + r.uniform(-.015, .015), LNG + r.uniform(-.015, .015)) for i in range(k)]


def biz(**kw):
    d = dict(lat=LAT, lng=LNG, price=1500.0, quality=0.6, marketing_spend=15000.0, capacity={})
    d.update(kw)
    return BusinessInputs(**d)


def pop_for(arch_key="membership", n=3000, seed=5, **kw):
    arch = ARCHETYPES[arch_key]
    return build_population(arch, zones(), comps(), kw.pop("b", biz()), ResolvedParams.from_archetype(arch), 1500.0, n_agents=n, seed=seed,
                            age_sex=None, spacing_km=0.35, profile=kw.pop("profile", None), offer=kw.pop("offer", None), overrides=None,
                            month0=0, days=84)


def test_genome_has_exactly_615_unique_parameters():
    assert gm.GENOME_SIZE == 615 == len(gm.REG) == len(set(gm.KEYS))


def test_every_parameter_is_consumed_by_the_model():
    counts = gm.audit()  # raises if any generated parameter is decorative
    assert sum(counts.values()) == 615


def test_population_genome_shape_and_finiteness():
    p = pop_for(n=2000)
    assert p.gen.G.shape == (2000, 615)
    gen_cols = [i for i, q in enumerate(gm.REG) if q.origin == "generated"]
    assert np.isfinite(p.gen.G[:, gen_cols]).all()


def test_deterministic_for_same_seed():
    a, b = pop_for(seed=9), pop_for(seed=9)
    assert np.array_equal(a.gen.G, b.gen.G, equal_nan=True)
    assert not np.array_equal(a.gen.G, pop_for(seed=10).gen.G, equal_nan=True)


def test_conditioning_income_segment_shifts_latent_income():
    p = pop_for(n=6000)
    inc = p.gen.G[:, gm.KI["lt_income"]]
    keys = [s.key for s in ARCHETYPES["membership"].segments]
    budget, premium = keys.index("budget"), keys.index("premium")
    assert inc[p.seg == premium].mean() > inc[p.seg == budget].mean() + 0.8


def test_age_drives_digital_nativity_negatively():
    p = pop_for(n=6000)
    d = p.gen.G[:, gm.KI["lt_digital"]]
    assert np.corrcoef(p.age, d)[0, 1] < -0.2


def test_women_value_women_friendly_environment_more():
    p = pop_for(n=6000)
    imp = p.gen.G[:, gm.KI["im_women_friendly"]]
    assert imp[p.female].mean() > imp[~p.female].mean() + 0.1


def test_opening_hours_change_time_fit():
    early = pop_for(offer={"open_hour": 5, "close_hour": 23})
    narrow = pop_for(offer={"open_hour": 11, "close_hour": 15})
    assert early.up.parts["time_fit"][:, 0].mean() > narrow.up.parts["time_fit"][:, 0].mean() + 0.1


def test_positioning_raises_your_attribute_utility():
    plain = pop_for()
    premium = pop_for(profile={"positioning": ["Premium experience", "Better service"]})
    assert premium.up.parts["attributes"][:, 0].mean() > plain.up.parts["attributes"][:, 0].mean()


def test_parse_hours():
    assert gm.parse_hours("6am–10pm") == (6, 22)
    assert gm.parse_hours("06:00-22:30") == (6, 22.5)
    assert gm.parse_hours("24x7") == (0, 24)
    assert gm.parse_hours("whenever") is None


def test_run_reports_genome_and_decomposition():
    arch = ARCHETYPES["membership"]
    r = run_abm(arch, zones(), comps(), biz(), ResolvedParams.from_archetype(arch), 1500.0, n_agents=2500, days=42, radius_km=2.0, cache_key="t1")
    assert r["genome"]["per_agent"] == 615
    assert r["genome"]["total_parameters"] == 2500 * 615
    assert len(r["agents"]["rows"]) == 2500
    assert set(r["decomposition"]) == {"chose_you", "chose_competitor", "chose_none"}
    assert "multiplier" in r["calibration"]


def test_explain_one_agent():
    arch = ARCHETYPES["membership"]
    r = run_abm(arch, zones(), comps(), biz(), ResolvedParams.from_archetype(arch), 1500.0, n_agents=1500, days=30, cache_key="t2")
    from app.engine.abm import cache_get
    p = cache_get("t2")
    ci = r["agents"]["columns"].index("last_choice")
    i = next(k for k, row in enumerate(r["agents"]["rows"]) if row[r["agents"]["columns"].index("in_market")])
    x = gm.explain(i, p.gen, p.up, p.names, r["agents"]["rows"][i][ci], gm.percentiles(p.gen.G))
    assert len(x["genome"]) == 615 and len(x["percentile"]) == 615
    assert x["options"] and all(set(o["parts"]) == set(gm.CHANNEL_GROUPS) for o in x["options"])


def test_calibration_raises_participation_when_incumbents_starve():
    arch = ARCHETYPES["membership"]
    tiny = [Zone(LAT + a, LNG + b, 40.0, 0.0) for a in np.linspace(-.01, .01, 6) for b in np.linspace(-.01, .01, 6)]
    r = run_abm(arch, tiny, comps(6), biz(), ResolvedParams.from_archetype(arch), 1500.0, n_agents=1500, days=30, radius_km=3.0)
    assert r["calibration"]["applied"] and 1.0 < r["calibration"]["multiplier"] <= 2.5
    off = run_abm(arch, tiny, comps(6), biz(), ResolvedParams.from_archetype(arch), 1500.0, n_agents=1500, days=30, radius_km=3.0,
                  overrides={"calibrate_incumbents": 0})
    assert not off["calibration"]["applied"]


def test_overnight_hours_wrap_past_midnight():
    night = pop_for(offer={"open_hour": 18, "close_hour": 2})
    assert night.meta["hours_mask"][0].sum() == 8
