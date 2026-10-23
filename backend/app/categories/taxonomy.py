"""Open category taxonomy.

This is a *seed* catalogue mapping everyday business phrases to OpenStreetMap
tag filters and an economic archetype. It is not a closed list: the resolver
(``resolver.py``) fuzzy-matches free text against it, optionally asks an LLM
for an OSM tag mapping that is then validated against an allow-list of tag
keys, and finally falls back to a name-keyword search so any business type can
be analysed.

Filters are Overpass QL tag selectors. Several filters are OR-ed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxonomyEntry:
    key: str
    label: str
    archetype: str
    filters: tuple[str, ...]
    synonyms: tuple[str, ...] = ()


def _e(key, label, archetype, filters, synonyms=()):
    return TaxonomyEntry(key, label, archetype, tuple(filters), tuple(synonyms))


TAXONOMY: tuple[TaxonomyEntry, ...] = (
    # --- membership ---
    _e("gym", "Gym / fitness centre", "membership", ['["leisure"="fitness_centre"]', '["amenity"="gym"]', '["sport"="fitness"]', '["name"~"(^| )gym( |$)|fitness|cult.?fit|gold.?s gym|anytime fitness|snap fitness|talwalkar|crossfit|f45",i]["leisure"!="pitch"]'], ("fitness", "workout", "crossfit", "bodybuilding", "health club", "jim")),
    _e("yoga_studio", "Yoga studio", "membership", ['["sport"="yoga"]', '["leisure"="fitness_centre"]["sport"~"yoga"]', '["name"~"yoga",i]'], ("yoga", "pilates", "meditation centre")),
    _e("dance_school", "Dance school", "membership", ['["leisure"="dance"]', '["amenity"="dancing_school"]', '["name"~"dance",i]'], ("dance class", "dance academy", "zumba")),
    _e("martial_arts", "Martial arts dojo", "membership", ['["sport"~"karate|judo|taekwondo|martial_arts|boxing"]'], ("karate", "boxing", "mma", "taekwondo", "judo")),
    _e("swimming", "Swimming pool / academy", "membership", ['["leisure"="swimming_pool"]["access"!="private"]', '["sport"="swimming"]'], ("swimming", "pool")),
    _e("coaching_centre", "Coaching / tuition centre", "membership", ['["amenity"="prep_school"]', '["amenity"="training"]', '["name"~"coaching|tuition|classes|academy|institute",i]'], ("tuition", "coaching", "classes", "test prep", "iit", "neet", "jee", "upsc", "tutor")),
    _e("language_school", "Language school", "membership", ['["amenity"="language_school"]'], ("english speaking", "ielts", "language classes", "spoken english")),
    _e("music_school", "Music school", "membership", ['["amenity"="music_school"]'], ("music class", "guitar class", "piano lessons")),
    _e("driving_school", "Driving school", "membership", ['["amenity"="driving_school"]'], ("driving lessons", "motor training")),
    _e("coworking", "Co-working space", "membership", ['["amenity"="coworking_space"]', '["office"="coworking"]'], ("cowork", "shared office", "hot desk")),
    _e("library", "Self-study library / reading room", "membership", ['["amenity"="library"]', '["name"~"library|study point|reading room",i]'], ("study library", "reading room", "self study")),
    _e("kindergarten", "Preschool / daycare", "membership", ['["amenity"="kindergarten"]', '["amenity"="childcare"]'], ("playschool", "play school", "daycare", "creche", "montessori")),
    _e("sports_club", "Sports academy / turf", "membership", ['["leisure"="sports_centre"]', '["leisure"="pitch"]["access"!="private"]'], ("turf", "cricket academy", "football academy", "badminton court", "sports academy")),
    _e("pg_hostel", "PG / hostel (monthly)", "membership", ['["tourism"="hostel"]', '["name"~"paying guest| pg|hostel",i]'], ("paying guest", "pg", "student hostel")),
    # --- dine in ---
    _e("cafe", "Café", "dine_in", ['["amenity"="cafe"]', '["amenity"]["name"~"coffee|chaayos|chai point|starbucks|barista|blue tokai|third wave|costa coffee|tim hortons|caf[eé]( |$)",i]', '["shop"="coffee"]'], ("coffee shop", "coffee", "tea house", "chai", "cafe")),
    _e("restaurant", "Restaurant", "dine_in", ['["amenity"="restaurant"]'], ("dhaba", "eatery", "dining", "family restaurant", "fine dining")),
    _e("bar", "Bar / pub", "dine_in", ['["amenity"~"^(bar|pub|biergarten)$"]'], ("pub", "brewery", "lounge", "bar")),
    _e("ice_cream", "Ice cream / dessert parlour", "dine_in", ['["amenity"="ice_cream"]', '["shop"="ice_cream"]', '["cuisine"~"ice_cream|dessert",i]'], ("ice cream", "dessert", "gelato", "kulfi")),
    _e("juice_bar", "Juice / smoothie bar", "dine_in", ['["cuisine"~"juice|smoothie",i]', '["name"~"juice|smoothie|shake",i]'], ("juice", "smoothie", "shake bar")),
    _e("food_court", "Food court / canteen", "dine_in", ['["amenity"="food_court"]'], ("canteen", "mess", "food court")),
    _e("tea_stall", "Tea / snack stall", "dine_in", ['["cuisine"~"tea|chai",i]', '["shop"="tea"]'], ("chai stall", "tea stall", "tapri")),
    _e("bakery_cafe", "Bakery café", "dine_in", ['["shop"="bakery"]'], ("patisserie", "cake shop")),
    # --- takeaway ---
    _e("pizza", "Pizza outlet", "takeaway", ['["cuisine"~"pizza",i]', '["name"~"pizza|pizzeria|domino|la pino|oven story|papa john|sbarro",i]', '["brand"~"domino|pizza hut|la pino|papa john|oven story|mojo pizza|chicago pizza|us pizza|smokin|pizza express|sbarro|little caesars",i]'], ("pizza", "pizzeria", "pizza shop")),
    _e("fast_food", "Fast food / QSR", "takeaway", ['["amenity"="fast_food"]'], ("burger", "qsr", "fast food", "fries", "shawarma", "momos", "rolls")),
    _e("cloud_kitchen", "Cloud kitchen / tiffin", "takeaway", ['["amenity"="fast_food"]', '["cuisine"~"indian|north_indian|south_indian|chinese",i]["amenity"~"restaurant|fast_food"]'], ("cloud kitchen", "tiffin", "dabba", "home food", "ghost kitchen")),
    _e("bakery", "Bakery (takeaway)", "takeaway", ['["shop"~"^(bakery|pastry|confectionery)$"]'], ("cakes", "bakery", "pastry", "sweets", "mithai", "halwai")),
    _e("biryani", "Biryani outlet", "takeaway", ['["cuisine"~"biryani",i]', '["name"~"biryani",i]'], ("biryani",)),
    _e("chinese_takeaway", "Chinese / momos takeaway", "takeaway", ['["cuisine"~"chinese|momo|tibetan",i]'], ("chinese", "momos", "noodles")),
    _e("street_food", "Street food / chaat", "takeaway", ['["cuisine"~"chaat|street_food|indian_street",i]', '["name"~"chaat|pani puri|golgappa",i]'], ("chaat", "pani puri", "golgappa", "vada pav", "street food")),
    # --- retail ---
    _e("pharmacy", "Pharmacy / chemist", "retail", ['["amenity"="pharmacy"]', '["shop"="chemist"]', '["healthcare"="pharmacy"]', '["shop"]["name"~"pharma|chemist|medical|apollo|medplus|wellness forever|netmeds|frank ross|guardian",i]'], ("chemist", "medical store", "medicine shop", "drugstore")),
    _e("grocery", "Grocery / kirana", "retail", ['["shop"~"^(convenience|supermarket|grocery|general|greengrocer)$"]', '["shop"]["name"~"kirana|general store|provision|reliance (fresh|smart)|more (supermarket|retail)|d-?mart|big bazaar|spencer|easyday|star bazaar|nature.?s basket",i]'], ("kirana", "grocery", "supermarket", "general store", "provision store", "mart")),
    _e("fruit_veg", "Fruit & vegetable shop", "retail", ['["shop"="greengrocer"]'], ("vegetables", "sabzi", "fruits", "greengrocer")),
    _e("butcher", "Meat / fish shop", "retail", ['["shop"~"^(butcher|seafood)$"]'], ("chicken shop", "meat", "mutton", "fish", "butcher")),
    _e("dairy", "Dairy / milk booth", "retail", ['["shop"="dairy"]'], ("milk", "dairy", "paneer")),
    _e("clothing", "Clothing / apparel store", "retail", ['["shop"~"^(clothes|boutique|fashion)$"]'], ("apparel", "boutique", "garments", "fashion", "kurti", "saree", "clothes")),
    _e("shoes", "Footwear store", "retail", ['["shop"="shoes"]'], ("shoes", "footwear", "sneakers")),
    _e("electronics", "Electronics / mobile store", "retail", ['["shop"~"^(electronics|mobile_phone|computer)$"]'], ("mobile shop", "phone store", "electronics", "laptop", "computer shop")),
    _e("hardware", "Hardware / paints", "retail", ['["shop"~"^(hardware|doityourself|paint)$"]'], ("hardware", "paint shop", "sanitary")),
    _e("stationery", "Stationery / books", "retail", ['["shop"~"^(stationery|books)$"]'], ("stationery", "bookstore", "books", "copy shop")),
    _e("jewelry", "Jewellery store", "retail", ['["shop"="jewelry"]'], ("jewellery", "jewelry", "gold", "silver")),
    _e("optician", "Optical store", "retail", ['["shop"="optician"]'], ("optician", "spectacles", "eyewear", "optical")),
    _e("cosmetics", "Cosmetics / beauty store", "retail", ['["shop"~"^(cosmetics|beauty|perfumery)$"]'], ("makeup", "cosmetics", "perfume")),
    _e("pet_shop", "Pet store", "retail", ['["shop"="pet"]'], ("pet shop", "pet food", "aquarium")),
    _e("florist", "Florist / gifts", "retail", ['["shop"~"^(florist|gift)$"]'], ("flowers", "gift shop", "florist")),
    _e("furniture", "Furniture / home store", "retail", ['["shop"~"^(furniture|interior_decoration|houseware)$"]'], ("furniture", "home decor", "interiors")),
    _e("liquor", "Liquor store", "retail", ['["shop"~"^(alcohol|wine|beverages)$"]'], ("wine shop", "liquor", "theka", "beer shop")),
    _e("sports_shop", "Sports goods store", "retail", ['["shop"~"^(sports|outdoor|bicycle)$"]'], ("sports shop", "cycle shop", "bicycle")),
    _e("toy_shop", "Toy store", "retail", ['["shop"~"^(toys|baby_goods)$"]'], ("toys", "baby store")),
    _e("fuel", "Fuel station", "retail", ['["amenity"="fuel"]'], ("petrol pump", "gas station", "fuel")),
    _e("ev_charging", "EV charging station", "retail", ['["amenity"="charging_station"]'], ("ev charging", "charging station")),
    # --- appointment ---
    _e("salon", "Hair salon / barber", "appointment", ['["shop"~"^(hairdresser|barber|beauty)$"]', '["shop"]["name"~"salon|parlou?r|barber|naturals|lakme|jawed habib|toni|looks|enrich|green trends|hair",i]'], ("barber", "haircut", "salon", "parlour", "unisex salon", "hair")),
    _e("beauty_salon", "Beauty parlour / spa", "appointment", ['["shop"~"^(beauty|massage)$"]', '["leisure"="spa"]', '["amenity"="spa"]'], ("beauty parlour", "spa", "massage", "nail art", "makeup artist", "facial")),
    _e("clinic", "General clinic", "appointment", ['["amenity"~"^(clinic|doctors)$"]', '["healthcare"~"^(clinic|doctor)$"]'], ("clinic", "doctor", "gp", "general physician", "polyclinic")),
    _e("dentist", "Dental clinic", "appointment", ['["amenity"="dentist"]', '["healthcare"="dentist"]'], ("dentist", "dental")),
    _e("physio", "Physiotherapy clinic", "appointment", ['["healthcare"="physiotherapist"]', '["name"~"physio",i]'], ("physiotherapy", "physio", "rehab")),
    _e("diagnostics", "Diagnostic / pathology lab", "appointment", ['["healthcare"~"^(laboratory|sample_collection)$"]', '["name"~"diagnostic|pathology|path lab",i]'], ("path lab", "pathology", "diagnostic centre", "blood test")),
    _e("veterinary", "Veterinary clinic", "appointment", ['["amenity"="veterinary"]'], ("vet", "pet clinic", "animal hospital")),
    _e("pet_grooming", "Pet grooming", "appointment", ['["shop"="pet_grooming"]', '["name"~"groom",i]'], ("pet grooming", "dog grooming", "pet spa")),
    _e("car_repair", "Car / bike service", "appointment", ['["shop"~"^(car_repair|motorcycle_repair|tyres)$"]'], ("garage", "mechanic", "bike service", "car service", "car wash")),
    _e("car_wash", "Car wash", "appointment", ['["amenity"="car_wash"]'], ("car wash", "detailing")),
    _e("laundry", "Laundry / dry cleaner", "appointment", ['["shop"~"^(laundry|dry_cleaning)$"]'], ("laundry", "dry cleaning", "ironing", "dhobi")),
    _e("tailor", "Tailor", "appointment", ['["shop"="tailor"]', '["craft"="tailor"]'], ("tailor", "alteration", "stitching")),
    _e("phone_repair", "Phone / electronics repair", "appointment", ['["shop"~"^(mobile_phone|electronics_repair|computer)$"]', '["craft"="electronics_repair"]'], ("mobile repair", "phone repair", "laptop repair")),
    _e("photo_studio", "Photo studio", "appointment", ['["shop"="photo"]', '["craft"="photographer"]'], ("photo studio", "photographer")),
    _e("tattoo", "Tattoo studio", "appointment", ['["shop"="tattoo"]'], ("tattoo", "piercing")),
    _e("print_shop", "Printing / xerox", "appointment", ['["shop"~"^(copyshop|printing)$"]', '["craft"="printer"]'], ("xerox", "printing", "photocopy", "print shop")),
    # --- lodging ---
    _e("hotel", "Hotel", "lodging", ['["tourism"="hotel"]'], ("hotel", "inn", "resort")),
    _e("guest_house", "Guest house / homestay", "lodging", ['["tourism"~"^(guest_house|apartment|chalet)$"]'], ("homestay", "guest house", "bnb", "b&b", "lodge", "dharamshala")),
    _e("hostel", "Backpacker hostel", "lodging", ['["tourism"="hostel"]'], ("backpacker", "hostel", "dorm")),
    _e("banquet", "Banquet / event hall", "lodging", ['["amenity"~"^(events_venue|conference_centre)$"]', '["name"~"banquet|marriage hall|party hall",i]'], ("banquet hall", "wedding venue", "party hall", "event venue")),
)

# OSM keys an LLM-proposed mapping may use. Anything else is rejected.
ALLOWED_OSM_KEYS = {
    "amenity", "shop", "leisure", "tourism", "healthcare", "office", "craft",
    "sport", "cuisine", "club", "name", "brand",
}

# Activity points used as a demand proxy for "residents_and_activity" archetypes.
ACTIVITY_FILTERS: tuple[str, ...] = (
    '["amenity"~"^(university|college|school|hospital|bus_station|marketplace|cinema|place_of_worship)$"]',
    '["railway"~"^(station|halt)$"]',
    '["public_transport"="station"]',
    '["office"]',
    '["tourism"~"^(attraction|museum|viewpoint)$"]',
    '["shop"="mall"]',
)

# Context points of interest (factor engine). One Overpass query, classified by ``classify_poi``.
CONTEXT_FILTERS: tuple[str, ...] = (
    '["amenity"~"^(school|college|university|hospital|clinic|doctors|pharmacy|bank|atm|bus_station|parking|place_of_worship|marketplace|restaurant|cafe|fast_food|cinema|fuel|police|post_office|library|coworking_space)$"]',
    '["highway"="bus_stop"]',
    '["railway"~"^(station|halt|subway_entrance)$"]',
    '["public_transport"="station"]',
    '["leisure"~"^(park|playground|fitness_centre)$"]',
    '["shop"~"^(mall|supermarket|convenience)$"]',
    '["office"]',
    '["tourism"="hotel"]',
)
ACTIVITY_KINDS = {"school", "college", "university", "hospital", "rail_station", "office", "mall", "marketplace", "cinema", "hotel", "place_of_worship"}


def classify_poi(tags: dict) -> str | None:
    a, sh, le = tags.get("amenity"), tags.get("shop"), tags.get("leisure")
    if a in ("clinic", "doctors"):
        return "clinic"
    if a == "coworking_space":
        return "coworking"
    if a == "bus_station" or tags.get("highway") == "bus_stop":
        return "bus_stop"
    if tags.get("railway") in ("station", "halt", "subway_entrance") or tags.get("public_transport") == "station":
        return "rail_station"
    if a in ("school", "college", "university", "hospital", "pharmacy", "bank", "atm", "parking", "place_of_worship", "marketplace",
             "restaurant", "cafe", "fast_food", "cinema", "fuel", "police", "post_office", "library"):
        return a
    if le in ("park", "playground"):
        return le
    if le == "fitness_centre":
        return "gym"
    if sh in ("mall", "supermarket", "convenience"):
        return sh
    if "office" in tags:
        return "office"
    if tags.get("tourism") == "hotel":
        return "hotel"
    return None
