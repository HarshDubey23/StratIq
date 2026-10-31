"""Comprehensive regression tests for category resolution and competitor classification.

Asserts Phase 1 P0 fixes:
1. "dentist clinic" resolves to "dentist", never "clinic".
2. "medical clinic" resolves to "clinic", never "pharmacy".
3. "orthodontist" resolves to "dentist", never falling back to generic keyword search.
4. Competitor relationship classification strictly classifies spas as "irrelevant" for dental clinics.
5. Direct dental facilities are correctly identified from tags and names.
"""
import pytest

from app.categories.competitors import classify_competitor
from app.categories.resolver import rank_taxonomy, resolve_offline



@pytest.mark.parametrize(
    "query,expected_key,expected_archetype",
    [
        ("dentist clinic", "dentist", "appointment"),
        ("dental clinic", "dentist", "appointment"),
        ("dental hospital", "dentist", "appointment"),
        ("orthodontist", "dentist", "appointment"),
        ("orthodontics", "dentist", "appointment"),
        ("pediatric dentist", "dentist", "appointment"),
        ("medical clinic", "clinic", "appointment"),
        ("general clinic", "clinic", "appointment"),
        ("polyclinic", "clinic", "appointment"),
        ("physiotherapy clinic", "physio", "appointment"),
        ("physio", "physio", "appointment"),
        ("pharmacy", "pharmacy", "retail"),
        ("chemist", "pharmacy", "retail"),
        ("medical store", "pharmacy", "retail"),
        ("spa", "beauty_salon", "appointment"),
        ("beauty parlour", "beauty_salon", "appointment"),
        ("wellness spa", "beauty_salon", "appointment"),
        ("hair salon", "salon", "appointment"),
        ("barber shop", "salon", "appointment"),
        ("gym", "gym", "membership"),
        ("fitness centre", "gym", "membership"),
        ("cafe", "cafe", "dine_in"),
        ("restaurant", "restaurant", "dine_in"),
        ("pizza outlet", "pizza", "takeaway"),
        ("hotel", "hotel", "lodging"),
    ],
)
def test_category_resolution_correctness(query: str, expected_key: str, expected_archetype: str):
    res = resolve_offline(query)
    assert res.key == expected_key, f"Query '{query}' resolved to '{res.key}', expected '{expected_key}'"
    assert res.archetype == expected_archetype, f"Query '{query}' has archetype '{res.archetype}', expected '{expected_archetype}'"
    assert res.method == "taxonomy", f"Query '{query}' should resolve via taxonomy, got '{res.method}'"
    assert res.confidence >= 0.85, f"Query '{query}' confidence {res.confidence} was too low"
    assert not res.needs_confirmation, f"Query '{query}' should not require confirmation"


def test_dentist_vs_clinic_tie_breaking():
    """Ensure dentist clinic does not produce a score tie where clinic wins."""
    ranked = rank_taxonomy("dentist clinic", limit=5)
    keys = [e.key for e, s in ranked]
    assert keys[0] == "dentist", f"Top result must be dentist, got {keys[0]}"
    dentist_score = next(s for e, s in ranked if e.key == "dentist")
    clinic_score = next(s for e, s in ranked if e.key == "clinic")
    assert dentist_score > clinic_score, f"Dentist score ({dentist_score}) must exceed clinic score ({clinic_score})"


def test_medical_clinic_not_pharmacy():
    """Ensure medical clinic resolves to General clinic, not Pharmacy / chemist."""
    res = resolve_offline("medical clinic")
    assert res.key == "clinic"
    assert res.key != "pharmacy"


def test_dental_competitor_classification_excludes_spas():
    """Critical regression test: Spas and salons must NEVER be direct dental competitors."""
    spa_tags_list = [
        {"amenity": "spa"},
        {"leisure": "spa"},
        {"shop": "beauty"},
        {"shop": "massage"},
        {"amenity": "spa", "name": "Serenity Day Spa"},
        {"shop": "beauty", "name": "Loreal Beauty Salon"},
        {"leisure": "spa", "name": "Ayurvedic Rejuvenation Spa"},
    ]
    for tags in spa_tags_list:
        cl = classify_competitor("dentist", tags, tags.get("name", ""))
        assert cl.tier == "irrelevant", f"Spa POI {tags} misclassified as {cl.tier}"
        assert not cl.is_direct_or_partial, f"Spa POI {tags} marked as direct or partial competitor"
        assert "spa" in cl.reason.lower() or "beauty" in cl.reason.lower() or "non-dental" in cl.reason.lower()


def test_dental_competitor_classification_includes_dental_providers():
    """Ensure authentic dental providers are classified as direct competitors."""
    dental_pois = [
        ({"amenity": "dentist"}, "City Dental Clinic"),
        ({"healthcare": "dentist"}, "Smile Care"),
        ({"amenity": "clinic", "healthcare:speciality": "orthodontics"}, "Modern Orthodontics"),
        ({"amenity": "clinic"}, "Dr. Roy Dental Clinic"),
        ({"amenity": "doctors"}, "Apex Tooth and Implant Centre"),
    ]
    for tags, name in dental_pois:
        cl = classify_competitor("dentist", tags, name)
        assert cl.tier == "direct", f"Dental POI '{name}' misclassified as {cl.tier}"
        assert cl.is_direct_or_partial, f"Dental POI '{name}' must be marked as direct/partial"


def test_hospital_partial_dental_competitor_handling():
    """Hospitals with dental departments are partial competitors; general hospitals are adjacent."""
    general_hosp = classify_competitor("dentist", {"amenity": "hospital"}, "Max Super Speciality Hospital")
    assert general_hosp.tier == "adjacent"
    assert not general_hosp.is_direct_or_partial

    dental_hosp = classify_competitor("dentist", {"amenity": "hospital"}, "Government Dental Hospital & College")
    assert dental_hosp.tier == "direct" or dental_hosp.tier == "partial_service"
    assert dental_hosp.is_direct_or_partial


def test_gym_competitor_classification():
    """Verify gym classification isolates direct fitness competitors."""
    gym_cl = classify_competitor("gym", {"leisure": "fitness_centre"}, "Gold's Gym")
    assert gym_cl.tier == "direct"
    assert gym_cl.is_direct_or_partial

    yoga_cl = classify_competitor("gym", {"sport": "yoga"}, "Sivananda Yoga Centre")
    assert gym_cl.tier == "direct"
    assert yoga_cl.tier == "indirect_substitute"

    spa_cl = classify_competitor("gym", {"amenity": "spa"}, "Aura Spa")
    assert spa_cl.tier == "irrelevant"
