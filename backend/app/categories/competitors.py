"""Competitor Relationship and Classification Engine.

Implements the 6-tier competitor relationship framework:
1. DIRECT: Exact category match / direct functional competitor.
2. PARTIAL_SERVICE: Multi-service provider with verified department (e.g. hospital with dental unit).
3. INDIRECT_SUBSTITUTE: Alternative modality serving similar underlying demand.
4. ADJACENT: Complementary service or cross-patronage neighbor (e.g. pharmacy next to clinic).
5. CONTEXTUAL_POI: Area anchor or transit generator (e.g. metro station, school).
6. IRRELEVANT: Unrelated commercial or institutional facility (e.g. spa vs dental clinic).

Strict Scientific Principle:
Unrelated businesses (IRRELEVANT) must never enter the customer choice set as direct competitors.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

CompetitorTier = Literal[
    "direct",
    "partial_service",
    "indirect_substitute",
    "adjacent",
    "contextual",
    "irrelevant",
]


@dataclass(frozen=True)
class CompetitorClassification:
    tier: CompetitorTier
    confidence: float
    reason: str
    is_direct_or_partial: bool

    def as_dict(self) -> dict:
        return asdict(self)


_DENTAL_NAME_RE = re.compile(
    r"\b(dental|dentist|dentistry|orthodont|orthodontics|endodont|periodont|teeth|tooth|smile|oral|root\s*canal|maxillofacial)\b",
    re.IGNORECASE,
)

_SPA_BEAUTY_RE = re.compile(
    r"\b(spa|massage|parlour|parlor|salon|facial|beauty|wellness|ayurvedic\s*spa|unisex\s*salon)\b",
    re.IGNORECASE,
)

_PHARMACY_RE = re.compile(
    r"\b(pharmacy|chemist|druggist|medical\s*store|medicos|medicine)\b",
    re.IGNORECASE,
)


def classify_competitor(target_category_key: str, poi_tags: dict | None, poi_name: str = "") -> CompetitorClassification:
    """Classify a POI's competitive relationship relative to the target business category."""
    tags = poi_tags or {}
    name = (poi_name or tags.get("name") or "").strip()
    amenity = tags.get("amenity", "")
    healthcare = tags.get("healthcare", "")
    speciality = tags.get("healthcare:speciality", "")
    shop = tags.get("shop", "")
    leisure = tags.get("leisure", "")

    # Target: Dental Clinic / Dentist
    if target_category_key == "dentist":
        # 1. Direct Dental Match
        if amenity == "dentist" or healthcare == "dentist" or "orthodont" in speciality.lower() or "dent" in speciality.lower():
            return CompetitorClassification(
                tier="direct",
                confidence=0.98,
                reason="Verified dental clinic from OpenStreetMap amenity/healthcare=dentist tag.",
                is_direct_or_partial=True,
            )
        if _DENTAL_NAME_RE.search(name):
            return CompetitorClassification(
                tier="direct",
                confidence=0.92,
                reason=f"Identified as dental care provider by facility name: '{name}'.",
                is_direct_or_partial=True,
            )

        # 2. Spas, Salons, Wellness -> STRICTLY IRRELEVANT
        if amenity == "spa" or leisure == "spa" or shop in ("beauty", "massage", "hairdresser") or _SPA_BEAUTY_RE.search(name):
            return CompetitorClassification(
                tier="irrelevant",
                confidence=0.99,
                reason="Wellness spa, beauty parlour, or salon does not offer dental medical services.",
                is_direct_or_partial=False,
            )

        # 3. Hospitals -> Partial Service if dental, else Adjacent Anchor
        if amenity == "hospital" or healthcare == "hospital":
            if _DENTAL_NAME_RE.search(speciality) or _DENTAL_NAME_RE.search(name):
                return CompetitorClassification(
                    tier="partial_service",
                    confidence=0.85,
                    reason="Hospital with verified dental department or dental specialty.",
                    is_direct_or_partial=True,
                )
            return CompetitorClassification(
                tier="adjacent",
                confidence=0.75,
                reason="General hospital providing healthcare anchor but dental department is unverified.",
                is_direct_or_partial=False,
            )

        # 4. Pharmacies -> Adjacent
        if amenity == "pharmacy" or shop == "chemist" or healthcare == "pharmacy" or _PHARMACY_RE.search(name):
            return CompetitorClassification(
                tier="adjacent",
                confidence=0.90,
                reason="Complementary pharmacy dispensing dental prescriptions and oral hygiene products.",
                is_direct_or_partial=False,
            )

        # 5. General Clinics / Doctors
        if amenity in ("clinic", "doctors") or healthcare in ("clinic", "doctor"):
            if _DENTAL_NAME_RE.search(name):
                return CompetitorClassification(
                    tier="direct",
                    confidence=0.90,
                    reason=f"Clinic named '{name}' verified as specialized dental practice.",
                    is_direct_or_partial=True,
                )
            return CompetitorClassification(
                tier="adjacent",
                confidence=0.70,
                reason="General medical clinic with non-dental or unverified outpatient services.",
                is_direct_or_partial=False,
            )

        # 6. Unrelated Commercial & Retail
        if amenity in ("restaurant", "cafe", "fast_food", "bank", "atm", "fuel") or shop in ("supermarket", "convenience", "clothes", "electronics"):
            return CompetitorClassification(
                tier="irrelevant",
                confidence=0.95,
                reason=f"Unrelated commercial activity ({amenity or shop}) with no healthcare competition.",
                is_direct_or_partial=False,
            )

        # Default fallback for dental
        return CompetitorClassification(
            tier="irrelevant",
            confidence=0.80,
            reason="Non-dental facility with no verified oral healthcare service.",
            is_direct_or_partial=False,
        )

    # Target: Gym / Fitness Centre
    elif target_category_key == "gym":
        if leisure == "fitness_centre" or amenity == "gym" or tags.get("sport") == "fitness":
            return CompetitorClassification(
                tier="direct",
                confidence=0.98,
                reason="Verified gym / fitness centre from leisure=fitness_centre tag.",
                is_direct_or_partial=True,
            )
        if tags.get("sport") in ("yoga", "boxing", "martial_arts", "pilates") or leisure == "sports_centre":
            return CompetitorClassification(
                tier="indirect_substitute",
                confidence=0.85,
                reason="Alternative fitness modality (yoga, martial arts, or sports centre).",
                is_direct_or_partial=False,
            )
        if amenity in ("dentist", "clinic", "hospital", "pharmacy"):
            return CompetitorClassification(
                tier="irrelevant",
                confidence=0.95,
                reason="Healthcare provider with no fitness competition.",
                is_direct_or_partial=False,
            )
        return CompetitorClassification(
            tier="irrelevant",
            confidence=0.75,
            reason="Unrelated commercial business.",
            is_direct_or_partial=False,
        )

    # Target: General Clinic
    elif target_category_key == "clinic":
        if (amenity in ("clinic", "doctors") or healthcare in ("clinic", "doctor")) and not (amenity == "dentist" or healthcare == "dentist"):
            return CompetitorClassification(
                tier="direct",
                confidence=0.95,
                reason="General medical clinic / doctor practice.",
                is_direct_or_partial=True,
            )
        if amenity == "dentist" or healthcare == "dentist":
            return CompetitorClassification(
                tier="adjacent",
                confidence=0.85,
                reason="Specialized dental clinic (complementary oral healthcare).",
                is_direct_or_partial=False,
            )
        if amenity == "hospital":
            return CompetitorClassification(
                tier="indirect_substitute",
                confidence=0.80,
                reason="Hospital outpatient department serving similar medical needs.",
                is_direct_or_partial=True,
            )
        if amenity == "spa" or leisure == "spa":
            return CompetitorClassification(
                tier="irrelevant",
                confidence=0.95,
                reason="Personal wellness/spa without general medical consultations.",
                is_direct_or_partial=False,
            )
        return CompetitorClassification(
            tier="irrelevant",
            confidence=0.75,
            reason="Unrelated business.",
            is_direct_or_partial=False,
        )

    # Default general classification
    is_exact = (
        target_category_key in amenity
        or target_category_key in shop
        or target_category_key in leisure
        or target_category_key in name.lower()
    )
    if is_exact:
        return CompetitorClassification(
            tier="direct",
            confidence=0.90,
            reason=f"Matches category '{target_category_key}' tags or title.",
            is_direct_or_partial=True,
        )
    return CompetitorClassification(
        tier="contextual",
        confidence=0.50,
        reason=f"Nearby business in catchment area of {target_category_key}.",
        is_direct_or_partial=False,
    )
