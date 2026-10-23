from app.providers.foursquare import merge_with_osm


def test_merge_dedupes_same_place_and_keeps_new():
    osm = [{"ref": "node/1", "lat": 28.6315, "lng": 77.2167, "name": "Domino's Pizza", "tags": {}}]
    fsq = [
        {"ref": "fsq/a", "lat": 28.6316, "lng": 77.2168, "name": "Dominos Pizza", "tags": {}},   # same shop, ~15 m away
        {"ref": "fsq/b", "lat": 28.6330, "lng": 77.2190, "name": "Pizza Wings", "tags": {}},     # not in OSM
    ]
    out, added = merge_with_osm(osm, fsq)
    assert added == 1
    assert [p["ref"] for p in out] == ["node/1", "fsq/b"]


def test_keywords_drop_generic_words():
    from app.providers.foursquare import _keywords
    assert _keywords(["pizza", "Pizza outlet"]) == ["pizza"]
    assert _keywords(["Gym / fitness centre"]) == ["gym", "fitness"]
