#!/usr/bin/env python3
"""
Fetches worldwide prayer rooms from OpenStreetMap and merges them with
any hand-curated entries already in places.json.

Only fetches amenity=prayer_room — mosques are handled by Apple Maps in-app.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "places.json")

# Only prayer rooms — not all mosques (that would be millions of records)
OVERPASS_QUERY = """
[out:json][timeout:180];
(
  node["amenity"="prayer_room"];
  way["amenity"="prayer_room"];
  relation["amenity"="prayer_room"];
);
out center tags;
"""

VENUE_TYPE_MAP = {
    "airport": "airport",
    "aerodrome": "airport",
    "terminal": "airport",
    "hospital": "hospital",
    "clinic": "hospital",
    "healthcare": "hospital",
    "university": "university",
    "college": "university",
    "school": "university",
    "office": "office",
    "government": "office",
    "mall": "shoppingCentre",
    "shopping_centre": "shoppingCentre",
    "shopping_center": "shoppingCentre",
    "retail": "shoppingCentre",
    "commercial": "shoppingCentre",
}


def fetch_osm(retries: int = 3) -> list:
    params = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    for attempt in range(1, retries + 1):
        try:
            print(f"  Attempt {attempt}/{retries}…")
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read()).get("elements", [])
        except urllib.error.HTTPError as e:
            print(f"  HTTP error {e.code}: {e.reason}")
            if e.code == 429:
                wait = 60 * attempt
                print(f"  Rate-limited — waiting {wait}s before retry")
                time.sleep(wait)
            elif attempt == retries:
                raise
            else:
                time.sleep(30)
        except Exception as e:
            print(f"  Error: {e}")
            if attempt == retries:
                raise
            time.sleep(30)
    return []


def get_lat_lon(el: dict):
    if el["type"] == "node":
        return el.get("lat"), el.get("lon")
    c = el.get("center")
    return (c.get("lat"), c.get("lon")) if c else (None, None)


def location_description(tags: dict) -> Optional[str]:
    floor = tags.get("addr:floor") or tags.get("level")
    if floor is not None:
        try:
            n = int(str(floor).strip())
            if n == 0:
                return "Ground Floor"
            elif n > 0:
                return f"Level {n}"
        except ValueError:
            pass
        text = str(floor).strip()
        if text:
            return text.title()
    desc = tags.get("description")
    return desc if desc and len(desc) <= 100 else None


def access_note(tags: dict) -> Optional[str]:
    a = tags.get("access", "")
    if a == "private":
        return "Private access only"
    if a == "customers":
        return "Customers only"
    if a == "no":
        return "No public access"
    return None


def venue_type(tags: dict) -> Optional[str]:
    for key in ("building", "location", "indoor", "landuse", "amenity:location"):
        val = tags.get(key, "").lower().replace(" ", "_")
        if val in VENUE_TYPE_MAP:
            return VENUE_TYPE_MAP[val]
    return None


def element_to_entry(el: dict) -> Optional[dict]:
    tags = el.get("tags", {})
    lat, lon = get_lat_lon(el)
    if lat is None or lon is None:
        return None

    name = (
        tags.get("name:en")
        or tags.get("name")
        or "Prayer Room"
    )
    if not name.strip():
        name = "Prayer Room"

    entry: dict = {
        "id": f"osm|{el['type']}|{el['id']}",
        "name": name,
        "kind": "prayerRoom",
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

    venue = tags.get("operator") or tags.get("brand") or tags.get("operator:en")
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
        print(f"  No existing file found at {path} — starting fresh")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("Fetching OSM prayer room data…")
    try:
        elements = fetch_osm()
    except Exception as e:
        print(f"Failed to fetch OSM data: {e}")
        raise SystemExit(1)
    print(f"  {len(elements)} OSM elements received")

    print("Loading existing curated entries…")
    existing = load_existing(OUTPUT_PATH)
    curated = {e["id"]: e for e in existing if not e["id"].startswith("osm|")}
    print(f"  {len(curated)} hand-curated entries preserved")

    print("Converting OSM elements…")
    osm_entries: dict[str, dict] = {}
    skipped = 0
    for el in elements:
        entry = element_to_entry(el)
        if entry:
            osm_entries[entry["id"]] = entry
        else:
            skipped += 1
    print(f"  {len(osm_entries)} entries converted, {skipped} skipped (no coordinates)")

    merged = list(curated.values()) + list(osm_entries.values())
    print(f"Total: {len(merged)} entries")

    out_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"Written → {out_path}")


if __name__ == "__main__":
    main()
