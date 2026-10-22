"""Assistant intent routing, money formatting, and OSM fallback filter parsing (offline)."""
from app.api.assistant import answer_from_facts, detect, inr, parse_price
from app.providers.osm import filter_terms
from app.providers.population import parse_age_sex


def test_inr_reads_indian_style():
    assert inr(42500) == "₹42,500"
    assert inr(342000) == "₹3.42 lakh"
    assert inr(12345678) == "₹1.23 crore"
    assert inr(-95000) == "minus ₹95,000"


def test_intents():
    assert detect("what is my profit") == "profit"
    assert detect("try price 1500") == "try_price"
    assert detect("kitne competitors hai") == "competitors"
    assert detect("show me the market map") == "navigate"
    assert detect("should I open here") == "verdict"
    assert detect("what is the break even") == "breakeven"
    assert parse_price("what if I charge 2,000 rupees") == 2000
    assert parse_price("test 1.5k price") == 1500


def test_answers_only_use_facts():
    f = {"project": "Gym CP", "business_type": "Gym", "unit": "members", "market": {"competitors_found": 2, "catchment_radius_km": 1.5,
         "nearest_competitors": [{"name": "Iron House", "distance_km": 0.4}, {"name": "Fit Hub", "distance_km": 1.1}],
         "population_in_catchment": 50000, "competitor_sources": ["OpenStreetMap (via Overpass API)"]},
         "baseline": None, "decision": None}
    a = answer_from_facts("competitors", f, "competitors?")
    assert "2 competitors" in a and "Iron House" in a
    assert "simulation" in answer_from_facts("profit", f, "profit?").lower()


def test_filter_terms_for_fallbacks():
    tags, words = filter_terms(['["leisure"="fitness_centre"]', '["amenity"="gym"]', '["name"~"yoga|pilates",i]'])
    assert tags == ["leisure:fitness_centre", "amenity:gym"] and words == ["yoga", "pilates"]
    tags, _ = filter_terms(['["shop"~"^(convenience|supermarket)$"]'])
    assert tags == ["shop:convenience", "shop:supermarket"]


def test_age_sex_accepts_18_bands():
    rows = [{"class": i, "age": str(i), "male": 10, "female": 10} for i in range(18)]
    out = parse_age_sex({"agesexpyramid": rows})
    assert len(out["bands"]) == 17 and out["bands"][-1]["male"] == 20
