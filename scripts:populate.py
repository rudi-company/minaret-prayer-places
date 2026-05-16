import requests, json

QUERY = """
[out:json][timeout:300];
(
  node["amenity"="prayer_room"];
  way["amenity"="prayer_room"];
  relation["amenity"="prayer_room"];
);
out center tags;
"""

VENUE_KEYWORDS = {
    "airport": ["airport","terminal","flughafen","aéroport","aeroporto","aeropuerto","havalimanı"],
    "hospital": ["hospital","clinic","nhs","infirmary","medical centre","health centre","klinik","hôpital"],
    "university": ["university","college","campus","polytechnic","institute of technology"],
    "office": ["office","headquarters","council","civic centre"],
    "shoppingCentre": ["shopping","mall","centre commercial","einkaufszentrum"],
}

def venue_type(venue):
    if not venue: return None
    v = venue.lower()
    for t, kws in VENUE_KEYWORDS.items():
        if any(k in v for k in kws): return t
    return None

def convert(el):
    tags = el.get("tags", {})
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    if not lat or not lon: return None

    name = tags.get("name", "").strip() or "Prayer Room"
    venue = tags.get("operator", "").strip() or None
    floor = tags.get("addr:floor","").strip()
    level = tags.get("level","").strip()
    desc = tags.get("description","").strip()
    loc = floor or ("Ground Floor" if level in ("0","G","g") else f"Level {level}" if level else None) or (desc[:120] if desc else None)
    access = {"private":"Private access","customers":"Customers only"}.get(tags.get("access",""))
    parts = []
    if tags.get("addr:housenumber") and tags.get("addr:street"):
        parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
    elif tags.get("addr:street"): parts.append(tags["addr:street"])
    for k in ("addr:city","addr:postcode"):
        if tags.get(k): parts.append(tags[k])

    e = {"id": f"osm-{el['type']}-{el['id']}", "name": name, "kind": "prayerRoom",
         "latitude": lat, "longitude": lon}
    if venue: e["venue"] = venue
    vt = venue_type(venue)
    if vt: e["venueType"] = vt
    if loc: e["locationDescription"] = loc
    if access: e["accessNote"] = access
    if parts: e["address"] = ", ".join(parts)
    for k,fk in [("website","website"),("contact:website","website"),("phone","phone"),
                  ("contact:phone","phone"),("opening_hours","openingHours")]:
        if tags.get(k) and fk not in e: e[fk] = tags[k]
    return e

print("Querying Overpass API...")
r = requests.post("https://overpass-api.de/api/interpreter", data={"data": QUERY}, timeout=360)
r.raise_for_status()
elements = r.json()["elements"]
print(f"  {len(elements)} elements from OSM")

osm = [e for el in elements if (e := convert(el))]
print(f"  {len(osm)} valid entries")

try:
    existing = json.load(open("places.json", encoding="utf-8"))
    curated = [e for e in existing if not e["id"].startswith("osm-")]
    print(f"  Keeping {len(curated)} hand-curated entries")
except FileNotFoundError:
    curated = []

combined = curated + osm
json.dump(combined, open("places.json","w",encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"Done — {len(combined)} total entries ({len(curated)} curated + {len(osm)} OSM)")