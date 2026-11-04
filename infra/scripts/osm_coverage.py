"""Count OSM objects per curated category around a place (coverage check, low volume).

  uv run --env-file ../../.env python ../../infra/scripts/osm_coverage.py Offenburg 30
Uses Nominatim once and one Overpass `out count` query per category, >=2 s apart,
with OSM_CONTACT in the User-Agent (OSM usage policies).
"""

import sys
import time

from app.providers import osm

place, radius = sys.argv[1], float(sys.argv[2])
point = osm.geocode(place, "Deutschland")
print(f"{place}: {point.latitude:.5f},{point.longitude:.5f} radius {radius} km")
total = 0
for label in osm.CATEGORIES:
    query = osm.build_query(point.latitude, point.longitude, radius, [label], [], 50)
    query = query.rsplit("out center", 1)[0] + "out count;"
    elements = osm.overpass(query, attempts=8).get("elements", [])
    n = int(elements[0]["tags"].get("total", 0)) if elements else 0
    total += n
    print(f"{label:32s} {n:5d}", flush=True)
    time.sleep(2)
print(f"{'Summe (mit Mehrfachzählung)':32s} {total:5d}")
