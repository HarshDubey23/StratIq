"""Field research: ground data from an industry field researcher becomes agent evidence."""
import pytest

from app.engine.field import field_evidence, wilson
from app.engine.model import ResolvedParams
from app.categories.archetypes import ARCHETYPES
from tests.test_api import project_payload, signup, stub_providers  # noqa: F401  (stub_providers is an autouse fixture)


def _iv(uses, visits=None, price=None, km=None):
    return {"kind": "interview", "data": {"uses_category": uses, "visits_per_month": visits, "max_price": price, "travel_km": km}}


def test_wilson_interval_contains_estimate_and_narrows_with_n():
    lo, hi = wilson(3, 10)
    assert lo < 0.3 < hi
    lo2, hi2 = wilson(30, 100)
    assert (hi2 - lo2) < (hi - lo)


def test_too_few_interviews_change_nothing():
    s = field_evidence([_iv(True, 4, 300, 2.0) for _ in range(3)])
    assert s.evidence == {}
    assert s.interviews["n"] == 3 and s.notes


def test_interviews_become_agent_parameters():
    recs = [_iv(True, 4, 300 + 20 * i, 1.0 + 0.5 * i) for i in range(10)] + [_iv(False) for _ in range(10)]
    s = field_evidence(recs)
    p = s.evidence["participation"]
    assert p[0] == pytest.approx(0.5) and p[1] < 0.5 < p[2] and p[3] == "field"
    assert s.evidence["frequency"][0] == pytest.approx(4.0)
    assert s.evidence["max_km"][0] >= 1.0
    assert 0.15 <= s.evidence["wtp_sigma"][0] <= 1.0
    # field evidence replaces the archetype assumption, a user override still wins
    rp = ResolvedParams.from_archetype(ARCHETYPES["dine_in"], {"max_km": 9.0}, s.evidence)
    assert rp.values["participation"] == pytest.approx(0.5) and rp.status["participation"] == "field"
    assert rp.values["max_km"] == 9.0 and rp.status["max_km"] == "user"


def test_structural_frequency_is_not_replaced():
    recs = [_iv(True, 6, 1500, 2) for _ in range(10)]
    assert "frequency" not in field_evidence(recs, frequency_fixed=True).evidence


def test_footfall_rent_and_competitor_prices_are_summarised():
    s = field_evidence([
        {"kind": "footfall", "data": {"count": 30, "minutes": 15}},
        {"kind": "footfall", "data": {"count": 60, "minutes": 15}},
        {"kind": "rent", "data": {"monthly_rent": 50000}},
        {"kind": "rent", "data": {"monthly_rent": 70000}},
        {"kind": "competitor", "data": {"name": "A", "price": 1200}},
    ]).public()
    assert s["footfall"]["people_per_hour"] == pytest.approx(180.0)
    assert s["rent"]["median"] == pytest.approx(60000)
    assert s["competitor_prices"]["n"] == 1


@pytest.mark.db
def test_field_flow_owner_and_researcher_link(client):
    signup(client, "field@example.com")
    p = client.post("/api/v1/projects", json=project_payload(client)).json()
    pid = p["id"]
    assert client.get(f"/api/v1/projects/{pid}/field").json()["request"] is None

    r = client.post(f"/api/v1/projects/{pid}/field/request", json={"researcher_name": "Asha", "brief": "Check gyms near the metro"})
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["request"]["token"]
    assert "Gym" in body["specialty"] or body["specialty"].endswith("specialist")

    # the researcher's link works without a session
    client.cookies.clear()
    brief = client.get(f"/api/v1/field/{token}").json()
    assert brief["project"]["name"] == "My gym" and "token" not in brief["request"]
    for i in range(10):
        ok = client.post(f"/api/v1/field/{token}/records", json={"kind": "interview", "data": {"uses_category": i < 3, "max_price": 1500 + 100 * i}})
        assert ok.status_code == 201, ok.text
    c = client.post(f"/api/v1/field/{token}/records", json={"kind": "competitor", "lat": 28.632, "lng": 77.218,
                                                           "data": {"name": "Iron Den", "price": 1400, "quality": 4}})
    assert c.status_code == 201 and c.json()["competitor_id"]
    assert client.post(f"/api/v1/field/{token}/records", json={"kind": "competitor", "data": {"name": "No pin"}}).status_code == 422
    assert client.post(f"/api/v1/field/{token}/records", json={"kind": "interview", "data": {"visits_per_month": 3}}).status_code == 422
    assert client.get("/api/v1/field/not-a-real-token-at-all-xxxx").status_code == 404
    assert client.post(f"/api/v1/field/{token}/submit").json()["status"] == "submitted"

    # back as the owner: evidence is computed and the field competitor is on the map
    client.post("/api/v1/auth/login", json={"email": "field@example.com", "password": "correct-horse-1"})
    f = client.get(f"/api/v1/projects/{pid}/field").json()
    assert f["summary"]["params"]["participation"]["value"] == pytest.approx(0.3)
    assert f["summary"]["params"]["participation"]["status"] == "field"
    lid = p["locations"][0]["id"]
    client.post(f"/api/v1/projects/{pid}/locations/{lid}/refresh", params={"wait": True})
    comps = client.get(f"/api/v1/projects/{pid}/market").json()["competitors"]
    field_c = [x for x in comps if x["source"] == "field"]
    assert field_c and field_c[0]["price"] == 1400 and field_c[0]["price_status"] == "field"
    base = next(s for s in client.get(f"/api/v1/projects/{pid}").json()["scenarios"] if s["is_baseline"])
    run = client.post(f"/api/v1/scenarios/{base['id']}/runs").json()
    assert run["status"] == "succeeded", run.get("error")
    assert run["results"]["parameter_status"]["participation"] == "field"
    assert run["results"]["evidence"]["n_field_competitors"] == 1
    assert client.get(f"/api/v1/projects/{pid}").json()["field"]["records"] == 11

    rid = c.json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}/field/records/{rid}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}").json()["field"]["records"] == 10
