#!/usr/bin/env python3
"""
Fetches worldwide prayer places from OpenStreetMap and merges them with
any hand-curated entries already in places.json.
"""

import json
import os
import re
import urllib.request
from typing import Optional

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "places.json")

OVERPASS_QUERY = """
[out:json][timeout:180];
(
  node["amenity"="prayer_room"];
  way["amenity"="prayer_room"];
  relation["amenity"="prayer_room"];
  node["amenity"="place_of_worship"]["religion"="muslim"];
  way["amenity"="place_of_worship"]["religion"="muslim"];
  relation["amenity"="place_of_worship"]["religion"="muslim"];
);
out center;
"""

VENUE_TYPE_MAP = {
    "airport": "airport",
    "aerodrome": "airport",
    "hospital": "hospital",
    "clinic": "hospital",
    "university": "university",
    "college": "university",
    "school": "university",
    "office": "office",
    "government": "office",
    "mall": "shoppingCentre",
    "shopping_centre": "shoppingCentre",
    "shopping_center": "shoppingCentre",
    "retail": "shoppingCentre",
}


def fetch_osm() -> list:
    data = OVERPASS_QUERY.encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read()).get("elements", [])


def get_lat_lon(el: dict):
    if el["type"] == "node":
        return el.get("lat"), el.get("lon")
    c = el.get("center")
    return (c.get("lat"), c.get("lon")) if c else (None, None)


def location_description(tags: dict) -> Optional[str]:
    floor = tags.get("addr:floor") or tags.get("level")
    if floor is not None:
        try:
            n = int(floor)
            return "Ground Floor" if n == 0 else f"Level {n}"
        except ValueError:
            return str(floor).title()
    desc = tags.get("description")
    return desc if desc and len(desc) <= 80 else None


def access_note(tags: dict) -> Optional[str]:
    a = tags.get("access")
    if a == "private":
        return "Private access only"
    if a == "customers":
        return "Customers only"
    return None


def venue_type(tags: dict) -> Optional[str]:
    for key in ("indoor", "location", "building", "landuse"):
        val = tags.get(key, "").lower()
        if val in VENUE_TYPE_MAP:
            return VENUE_TYPE_MAP[val]
    return None


def element_to_entry(el: dict) -> Optional[dict]:
    tags = el.get("tags", {})
    lat, lon = get_lat_lon(el)
    if lat is None or lon is None:
        return None

    amenity = tags.get("amenity", "")
    kind = "prayerRoom" if amenity == "prayer_room" else "mosque"
    name = (
        tags.get("name:en")
        or tags.get("name")
        or ("Prayer Room" if kind == "prayerRoom" else "Mosque")
    )

    entry = {
        "id": f"osm|{el['type']}|{el['id']}",
        "name": name,
        "kind": kind,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
    }

    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")]
    address = ", ".join(p for p in parts if p)
    if address:
        entry["address"] = address

    phone = tags.get("contact:phone") or tags.get("phone")
    if phone:
        entry["phone"] = phone

    website = tags.get("contact:website") or tags.get("website")
    if website:
        entry["website"] = website

    hours = tags.get("opening_hours")
    if hours:
        entry["openingHours"] = hours

    venue = tags.get("operator") or tags.get("brand")
    if venue:
        entry["venue"] = venue

    vt = venue_type(tags)
    if vt:
        entry["venueType"] = vt

    loc = location_description(tags)
    if loc:
        entry["locationDescription"] = loc

    an = access_note(tags)
    if an:
        entry["accessNote"] = an

    return entry


def load_existing(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("Fetching OSM data…")
    elements = fetch_osm()
    print(f"  {len(elements)} OSM elements received")

    print("Loading existing curated entries…")
    existing = load_existing(OUTPUT_PATH)
    curated = {e["id"]: e for e in existing if not e["id"].startswith("osm|")}
    print(f"  {len(curated)} hand-curated entries preserved")

    print("Converting OSM elements…")
    osm_entries = {}
    for el in elements:
        entry = element_to_entry(el)
        if entry:
            osm_entries[entry["id"]] = entry
    print(f"  {len(osm_entries)} OSM entries converted")

    merged = list(curated.values()) + list(osm_entries.values())
    print(f"Total: {len(merged)} entries")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"Written → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
