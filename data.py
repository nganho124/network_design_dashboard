"""
Sample/synthetic data for the demo.

Replace load_sample_data() with a real loader (CSV/Excel upload, DB query)
once you have real network data — the rest of the app doesn't care where
this comes from, as long as the three dataframes keep this shape.
"""

import pandas as pd
import numpy as np

# Rough coordinates so the map looks like a plausible European network
DC_LOCATIONS = {
    "DC_HAMBURG":  (53.5511, 9.9937),
    "DC_MUNICH":   (48.1351, 11.5820),
    "DC_BERLIN":   (52.5200, 13.4050),
    "DC_COLOGNE":  (50.9375, 6.9603),
}

REGION_LOCATIONS = {
    "REGION_NORTH":     (54.3233, 10.1228),
    "REGION_SOUTH":     (48.7758, 9.1829),
    "REGION_EAST":      (51.3397, 12.3731),
    "REGION_WEST":      (51.2277, 6.7735),
    "REGION_CENTRAL":   (50.1109, 8.6821),
}


def load_sample_data():
    """Returns (dcs, demand, distance) dataframes."""

    dcs = pd.DataFrame([
        {"dc_id": dc_id, "lat": lat, "lon": lon,
         "capacity_units": cap, "fixed_cost_eur": fixed}
        for (dc_id, (lat, lon)), cap, fixed in zip(
            DC_LOCATIONS.items(),
            [12000, 9000, 10000, 8000],
            [180_000, 150_000, 160_000, 140_000],
        )
    ])

    demand = pd.DataFrame([
        {"region_id": r, "lat": lat, "lon": lon, "demand_units": d}
        for (r, (lat, lon)), d in zip(
            REGION_LOCATIONS.items(),
            [3200, 4100, 2800, 3600, 2500],
        )
    ])

    # Simple haversine-based distance -> cost per unit (EUR), deterministic for demo
    def haversine(lat1, lon1, lat2, lon2):
        r = 6371
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlmb = np.radians(lon2 - lon1)
        a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
        return 2 * r * np.arcsin(np.sqrt(a))

    rows = []
    for _, dc in dcs.iterrows():
        for _, reg in demand.iterrows():
            dist_km = haversine(dc["lat"], dc["lon"], reg["lat"], reg["lon"])
            rows.append({
                "dc_id": dc["dc_id"],
                "region_id": reg["region_id"],
                "distance_km": round(dist_km, 1),
                "cost_per_unit_direct": round(0.08 * dist_km + 2, 2),   # EUR/unit
                "cost_per_unit_lsp": round(0.05 * dist_km + 3.5, 2),    # LSP: cheaper transport, higher handoff fee
                "days_to_serve_direct": round(dist_km / 500 + 0.5, 1),
                "days_to_serve_lsp": round(dist_km / 500 + 1.2, 1),     # LSP adds a day for handoff
            })
    distance = pd.DataFrame(rows)

    return dcs, demand, distance
