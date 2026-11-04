"""Count OSM objects per curated category around a place (coverage check).

  uv run --env-file ../../.env python ../../infra/scripts/osm_coverage.py Offenburg 30
With OSM_EXTRACT_PATH set, counts come from the local extract (no API load); otherwise one
Overpass `out count` query per category with backoff (public instance policy).
Only named objects are counted (same selection as discovery).
"""

import os
import sys
import time

from app.providers import osm

place, radius = sys.argv[1], float(sys.argv[2])
point = osm.geocode(place, "Deutschland")
extract = os.getenv("OSM_EXTRACT_PATH", "").strip()
print(f"{place}: {point.latitude:.5f},{point.longitude:.5f} radius {radius} km · source: "
      + (f"extract {os.path.basename(extract)}" if extract else "overpass"))
total = 0
for label in osm.CATEGORIES:
    if extract:
        n = len(osm.search_extract(extract, point, radius, [label], [], 100000)["elements"])
    else:
        query = osm.build_query(point.latitude, point.longitude, radius, [label], [], 50)
        query = query.rsplit("out center", 1)[0] + "out count;"
        elements = osm.overpass(query, attempts=8).get("elements", [])
        n = int(elements[0]["tags"].get("total", 0)) if elements else 0
        time.sleep(2)
    total += n
    print(f"{label:32s} {n:5d}", flush=True)
print(f"{'Summe (mit Mehrfachzählung)':32s} {total:5d}")
