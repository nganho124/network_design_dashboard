"""
Synthetic data generator — Germany network.

Structure: Supplier -> Warehouse (WH) -> Store

Design choices (per spec):
- 30% of suppliers are international, carrying ~60% of total supply volume,
  with longer lead times than domestic suppliers.
- 8 warehouses spread across Germany; capacity sized from the demand of
  stores in their catchment area (nearest-WH assignment + buffer).
- Total cost = inbound transport (supplier->WH) + storage/handling at WH
  + delivery (WH->store). Inventory holding/DIO can be layered in later.

Everything here is synthetic but geographically real (actual German city
coordinates), so distances and resulting costs behave plausibly.
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)  # fixed seed so demo results are repeatable

# ---------------------------------------------------------------------------
# Reference geography
# ---------------------------------------------------------------------------

# candidate cities for STORE demand (name, lat, lon, approx population '000s)
GERMAN_CITIES = [
    ("Hamburg", 53.5511, 9.9937, 1900), ("Berlin", 52.5200, 13.4050, 3700),
    ("Munich", 48.1351, 11.5820, 1500), ("Cologne", 50.9375, 6.9603, 1080),
    ("Frankfurt", 50.1109, 8.6821, 760), ("Stuttgart", 48.7758, 9.1829, 630),
    ("Leipzig", 51.3397, 12.3731, 600), ("Nuremberg", 49.4521, 11.0767, 520),
    ("Dortmund", 51.5136, 7.4653, 590), ("Essen", 51.4556, 7.0116, 580),
    ("Dresden", 51.0504, 13.7373, 560), ("Hannover", 52.3759, 9.7320, 540),
    ("Bremen", 53.0793, 8.8017, 570), ("Duisburg", 51.4344, 6.7623, 500),
    ("Bochum", 51.4818, 7.2162, 365), ("Wuppertal", 51.2562, 7.1508, 355),
    ("Bielefeld", 52.0302, 8.5325, 335), ("Bonn", 50.7374, 7.0982, 330),
    ("Mannheim", 49.4875, 8.4660, 310), ("Karlsruhe", 49.0069, 8.4037, 310),
    ("Wiesbaden", 50.0782, 8.2398, 280), ("Muenster", 51.9607, 7.6261, 315),
    ("Augsburg", 48.3705, 10.8978, 300), ("Aachen", 50.7753, 6.0839, 250),
    ("Moenchengladbach", 51.1805, 6.4428, 260), ("Braunschweig", 52.2689, 10.5268, 250),
    ("Chemnitz", 50.8278, 12.9214, 245), ("Kiel", 54.3233, 10.1228, 245),
    ("Halle", 51.4964, 11.9693, 240), ("Magdeburg", 52.1205, 11.6276, 235),
    ("Freiburg", 47.9990, 7.8421, 230), ("Krefeld", 51.3388, 6.5853, 225),
    ("Luebeck", 53.8655, 10.6866, 215), ("Oberhausen", 51.4963, 6.8638, 210),
    ("Erfurt", 50.9848, 11.0299, 215), ("Mainz", 49.9929, 8.2473, 220),
    ("Rostock", 54.0887, 12.1400, 210), ("Kassel", 51.3127, 9.4797, 200),
    ("Saarbruecken", 49.2401, 6.9969, 180), ("Potsdam", 52.3906, 13.0645, 185),
    # extended pool of mid/smaller towns for realistic 400-point spread
    ("Herne", 51.5386, 7.2201, 156), ("Neuss", 51.2043, 6.6879, 153),
    ("Paderborn", 51.7189, 8.7575, 151), ("Regensburg", 49.0134, 12.1016, 153),
    ("Ingolstadt", 48.7665, 11.4257, 138), ("Wuerzburg", 49.7913, 9.9534, 127),
    ("Fuerth", 49.4783, 10.9903, 128), ("Wolfsburg", 52.4227, 10.7865, 124),
    ("Offenbach", 50.1055, 8.7761, 128), ("Ulm", 48.4011, 9.9876, 126),
    ("Heidelberg", 49.3988, 8.6724, 160), ("Pforzheim", 48.8922, 8.6946, 126),
    ("Goettingen", 51.5412, 9.9158, 119), ("Bottrop", 51.5216, 6.9289, 117),
    ("Trier", 49.7499, 6.6371, 111), ("Recklinghausen", 51.6142, 7.1975, 111),
    ("Reutlingen", 48.4914, 9.2043, 116), ("Bremerhaven", 53.5396, 8.5809, 113),
    ("Koblenz", 50.3569, 7.5890, 114), ("Bergisch Gladbach", 50.9925, 7.1330, 112),
    ("Jena", 50.9271, 11.5892, 111), ("Remscheid", 51.1789, 7.1897, 111),
    ("Erlangen", 49.5897, 10.9877, 113), ("Moers", 51.4508, 6.6262, 104),
    ("Salzgitter", 52.1500, 10.4000, 104), ("Siegen", 50.8748, 8.0243, 101),
    ("Hildesheim", 52.1508, 9.9511, 101), ("Cottbus", 51.7563, 14.3329, 100),
    ("Kaiserslautern", 49.4401, 7.7491, 99), ("Guetersloh", 51.9067, 8.3773, 100),
    ("Witten", 51.4419, 7.3352, 96), ("Iserlohn", 51.3733, 7.7016, 93),
    ("Ratingen", 51.2966, 6.8497, 90), ("Hanau", 50.1319, 8.9165, 100),
    ("Zwickau", 50.7185, 12.4938, 90), ("Flensburg", 54.7937, 9.4362, 91),
    ("Schwerin", 53.6355, 11.4012, 95), ("Luenen", 51.6167, 7.5233, 86),
    ("Villingen-Schwenningen", 48.0611, 8.4569, 86), ("Konstanz", 47.6603, 9.1758, 85),
    ("Worms", 49.6327, 8.3577, 84), ("Marburg", 50.8021, 8.7686, 77),
    ("Neubrandenburg", 53.5583, 13.2611, 64), ("Detmold", 51.9367, 8.8790, 74),
    ("Giessen", 50.5860, 8.6786, 90), ("Ludwigshafen", 49.4741, 8.4353, 172),
    ("Offenburg", 48.4739, 7.9411, 60), ("Ravensburg", 47.7817, 9.6119, 50),
    ("Neumuenster", 54.0715, 9.9819, 79), ("Landshut", 48.5372, 12.1522, 74),
    ("Celle", 52.6234, 10.0824, 69), ("Delmenhorst", 53.0525, 8.6304, 78),
    ("Lippstadt", 51.6739, 8.3486, 68), ("Rheine", 52.2833, 7.4394, 77),
    ("Dorsten", 51.6608, 6.9647, 74),
]
# dedupe defensive (in case of accidental repeats above)
_seen = set()
GERMAN_CITIES = [c for c in GERMAN_CITIES if not (c[0] in _seen or _seen.add(c[0]))]

# 8 warehouse hub cities — spread for national coverage (N/S/E/W/Central)
WAREHOUSE_CITIES = [
    "Hamburg", "Berlin", "Munich", "Cologne",
    "Frankfurt", "Stuttgart", "Leipzig", "Nuremberg",
]

# international supplier hubs (name, country, lat, lon) — flavored to DIY/hardware sourcing patterns
INTL_SUPPLIER_HUBS = [
    ("Shanghai Hardware & Tools", "China", 31.2304, 121.4737),
    ("Shenzhen Power Tools", "China", 22.5431, 114.0579),
    ("Warsaw Building Materials", "Poland", 52.2297, 21.0122),
    ("Milan Fixtures & Design", "Italy", 45.4642, 9.1900),
    ("Istanbul Workwear & Textiles", "Turkey", 41.0082, 28.9784),
    ("Rotterdam Import Hub", "Netherlands", 51.9244, 4.4777),
]

# domestic supplier candidate cities (reuse German city list, different role)
DOMESTIC_SUPPLIER_CITIES = [
    "Dortmund", "Bielefeld", "Chemnitz", "Augsburg", "Magdeburg",
    "Braunschweig", "Krefeld", "Kassel", "Erfurt", "Mainz",
    "Saarbruecken", "Halle", "Bonn", "Muenster",
]

# product groups: (group_id, category, weight_kg_per_unit, volume_cbm_per_unit, unit_value_eur)
PRODUCT_GROUPS_RAW = [
    ("PG01", "Power Tools", 2.4, 0.015, 85), ("PG02", "Hand Tools", 0.8, 0.004, 22),
    ("PG03", "Fasteners", 0.05, 0.0002, 3), ("PG04", "Plumbing Fittings", 0.3, 0.001, 8),
    ("PG05", "Electrical Components", 0.4, 0.002, 15), ("PG06", "Paint & Coatings", 3.0, 0.005, 18),
    ("PG07", "Garden Equipment", 6.5, 0.04, 120), ("PG08", "Safety Gear (PPE)", 0.5, 0.003, 25),
    ("PG09", "Adhesives & Sealants", 1.2, 0.0015, 12), ("PG10", "Timber & Boards", 12.0, 0.08, 45),
    ("PG11", "Flooring Materials", 8.0, 0.03, 35), ("PG12", "HVAC Components", 5.5, 0.02, 95),
    ("PG13", "Hardware & Fixtures", 0.6, 0.002, 10), ("PG14", "Cleaning Supplies", 1.5, 0.003, 9),
    ("PG15", "Ladders & Access", 9.0, 0.06, 70), ("PG16", "Cabling & Wiring", 4.0, 0.01, 40),
    ("PG17", "Insulation Materials", 2.0, 0.05, 20), ("PG18", "Workwear & Apparel", 0.7, 0.004, 30),
]


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_product_groups() -> pd.DataFrame:
    return pd.DataFrame(PRODUCT_GROUPS_RAW, columns=[
        "group_id", "category", "weight_kg_per_unit", "volume_cbm_per_unit", "unit_value_eur",
    ])


def generate_warehouses() -> pd.DataFrame:
    city_lookup = {name: (lat, lon) for name, lat, lon, _ in GERMAN_CITIES}
    rows = []
    for i, city in enumerate(WAREHOUSE_CITIES, start=1):
        lat, lon = city_lookup[city]
        rows.append({"wh_id": f"WH_{city.upper()}", "city": city, "lat": lat, "lon": lon,
                     "handling_base_cost_eur_per_unit": round(RNG.uniform(0.8, 1.4), 2),
                     "fixed_cost_eur_per_month": int(RNG.uniform(35_000, 60_000))})
    return pd.DataFrame(rows)


def generate_stores(product_groups: pd.DataFrame, n_stores: int = 400):
    """Returns (stores_df, demand_df). One store per sampled city, demand scaled by population."""
    # sub-linear population weighting (pop^0.6) so mega-cities like Berlin don't
    # swallow the whole store network — retail footprints scale with population
    # but saturate; smaller towns still get realistic representation
    weights = np.array([pop for _, _, _, pop in GERMAN_CITIES], dtype=float) ** 0.6
    weights = weights / weights.sum()
    idx = RNG.choice(len(GERMAN_CITIES), size=n_stores, replace=True, p=weights)

    stores = []
    demand_rows = []
    for i, city_idx in enumerate(idx, start=1):
        name, lat, lon, pop = GERMAN_CITIES[city_idx]
        # jitter location slightly so multiple stores in the same city don't overlap exactly
        jlat, jlon = lat + RNG.uniform(-0.05, 0.05), lon + RNG.uniform(-0.05, 0.05)
        store_id = f"ST_{i:03d}_{name.upper()}"
        stores.append({"store_id": store_id, "city": name, "lat": jlat, "lon": jlon})

        base_demand = pop * RNG.uniform(0.4, 0.7)  # rough units/month scaling from population
        for _, pg in product_groups.iterrows():
            share = RNG.dirichlet(np.ones(1))[0]  # placeholder, replaced below for realism
            demand_rows.append({
                "store_id": store_id, "group_id": pg["group_id"],
                "demand_units": max(1, int(base_demand * RNG.uniform(0.02, 0.08))),
            })

    return pd.DataFrame(stores), pd.DataFrame(demand_rows)


def generate_suppliers(n_suppliers: int = 20, intl_count_share: float = 0.30,
                        intl_volume_share: float = 0.60) -> pd.DataFrame:
    n_intl = max(1, round(n_suppliers * intl_count_share))
    n_dom = n_suppliers - n_intl

    intl_hubs = [INTL_SUPPLIER_HUBS[i % len(INTL_SUPPLIER_HUBS)] for i in range(n_intl)]
    dom_cities = [DOMESTIC_SUPPLIER_CITIES[i % len(DOMESTIC_SUPPLIER_CITIES)] for i in range(n_dom)]
    city_lookup = {name: (lat, lon) for name, lat, lon, _ in GERMAN_CITIES}

    rows = []
    # raw volume weights so international suppliers collectively land near intl_volume_share
    intl_raw = RNG.dirichlet(np.ones(n_intl)) * intl_volume_share
    dom_raw = RNG.dirichlet(np.ones(n_dom)) * (1 - intl_volume_share)

    for i, (name, country, lat, lon) in enumerate(intl_hubs):
        rows.append({
            "supplier_id": f"SUP_INTL_{i+1:02d}", "name": f"{name} {i+1}", "country": country,
            "type": "international", "lat": lat, "lon": lon,
            "lead_time_days": int(RNG.uniform(25, 45)),
            "volume_share": round(intl_raw[i], 4),
        })
    for i, city in enumerate(dom_cities):
        lat, lon = city_lookup[city]
        rows.append({
            "supplier_id": f"SUP_DOM_{i+1:02d}", "name": f"{city} Supplier", "country": "Germany",
            "type": "domestic", "lat": lat, "lon": lon,
            "lead_time_days": int(RNG.uniform(2, 7)),
            "volume_share": round(dom_raw[i], 4),
        })

    return pd.DataFrame(rows)


def generate_supply_share(suppliers: pd.DataFrame, product_groups: pd.DataFrame,
                           suppliers_per_group: int = 3) -> pd.DataFrame:
    """Fixed Supplier -> (implicitly all WHs) share per product group, weighted by supplier volume_share."""
    rows = []
    for _, pg in product_groups.iterrows():
        chosen = suppliers.sample(n=min(suppliers_per_group, len(suppliers)),
                                   weights=suppliers["volume_share"], random_state=RNG.integers(0, 1e6))
        shares = RNG.dirichlet(chosen["volume_share"].values + 0.01)
        for (_, sup), share in zip(chosen.iterrows(), shares):
            rows.append({"group_id": pg["group_id"], "supplier_id": sup["supplier_id"],
                         "share": round(float(share), 3)})
    return pd.DataFrame(rows)


def assign_stores_to_nearest_wh(stores: pd.DataFrame, warehouses: pd.DataFrame) -> pd.Series:
    assignments = []
    for _, s in stores.iterrows():
        dists = warehouses.apply(lambda w: _haversine(s["lat"], s["lon"], w["lat"], w["lon"]), axis=1)
        assignments.append(warehouses.loc[dists.idxmin(), "wh_id"])
    return pd.Series(assignments, index=stores["store_id"], name="nearest_wh_id")


def size_warehouse_capacity(warehouses: pd.DataFrame, stores: pd.DataFrame,
                             demand: pd.DataFrame, buffer: float = 1.15,
                             min_ratio: float = 0.35, max_ratio: float = 2.5) -> pd.DataFrame:
    """
    Capacity = nearest-catchment demand * buffer, but floored/capped relative
    to an even split across warehouses. Pure nearest-neighbor assignment lets
    one metro area (e.g. Berlin) dominate and starves smaller regions down to
    unrealistically tiny capacity — the floor/cap keeps every warehouse
    plausibly sized for a real regional network.
    """
    nearest = assign_stores_to_nearest_wh(stores, warehouses).reset_index()
    demand_with_wh = demand.merge(nearest, on="store_id")
    cap_by_wh = demand_with_wh.groupby("nearest_wh_id")["demand_units"].sum() * buffer

    n_wh = len(warehouses)
    even_split = demand["demand_units"].sum() * buffer / n_wh
    floor, ceiling = even_split * min_ratio, even_split * max_ratio

    warehouses = warehouses.copy()
    raw_cap = warehouses["wh_id"].map(cap_by_wh).fillna(0)
    warehouses["capacity_units"] = raw_cap.clip(lower=floor, upper=ceiling).astype(int)
    return warehouses


def compute_inbound_transport_cost(suppliers: pd.DataFrame, warehouses: pd.DataFrame) -> pd.DataFrame:
    """Cost per unit, supplier -> each WH. International adds a flat customs/ocean-freight base fee."""
    rows = []
    for _, sup in suppliers.iterrows():
        for _, wh in warehouses.iterrows():
            dist_km = _haversine(sup["lat"], sup["lon"], wh["lat"], wh["lon"])
            if sup["type"] == "international":
                cost = 8.5 + 0.015 * dist_km   # base ocean/customs fee + inland leg
            else:
                cost = 0.06 * dist_km + 1.0    # domestic trucking
            rows.append({"supplier_id": sup["supplier_id"], "wh_id": wh["wh_id"],
                        "distance_km": round(dist_km, 1), "cost_per_unit_eur": round(cost, 2),
                        "lead_time_days": sup["lead_time_days"]})
    return pd.DataFrame(rows)


def compute_delivery_cost(warehouses: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    """Cost per unit, WH -> store."""
    rows = []
    for _, wh in warehouses.iterrows():
        for _, s in stores.iterrows():
            dist_km = _haversine(wh["lat"], wh["lon"], s["lat"], s["lon"])
            cost = 0.09 * dist_km + 1.5
            days = round(dist_km / 550 + 0.4, 2)
            rows.append({"wh_id": wh["wh_id"], "store_id": s["store_id"],
                        "distance_km": round(dist_km, 1), "cost_per_unit_eur": round(cost, 2),
                        "days_to_serve": days})
    return pd.DataFrame(rows)


def build_all_data(n_stores: int = 400, n_suppliers: int = 20):
    product_groups = generate_product_groups()
    warehouses = generate_warehouses()
    stores, demand = generate_stores(product_groups, n_stores=n_stores)
    warehouses = size_warehouse_capacity(warehouses, stores, demand)
    suppliers = generate_suppliers(n_suppliers=n_suppliers)
    supply_share = generate_supply_share(suppliers, product_groups)
    inbound_cost = compute_inbound_transport_cost(suppliers, warehouses)
    delivery_cost = compute_delivery_cost(warehouses, stores)

    return {
        "product_groups": product_groups,
        "warehouses": warehouses,
        "stores": stores,
        "demand": demand,
        "suppliers": suppliers,
        "supply_share": supply_share,
        "inbound_cost": inbound_cost,
        "delivery_cost": delivery_cost,
    }


if __name__ == "__main__":
    data = build_all_data()
    for name, df in data.items():
        print(f"\n=== {name} ({len(df)} rows) ===")
        print(df.head(4).to_string(index=False))

    intl_volume = data["suppliers"].loc[data["suppliers"]["type"] == "international", "volume_share"].sum()
    print(f"\nInternational supplier count share: "
          f"{(data['suppliers']['type'] == 'international').mean():.0%}")
    print(f"International supplier volume share: {intl_volume:.0%}")
    print(f"Total warehouse capacity: {data['warehouses']['capacity_units'].sum():,} units")
    print(f"Total demand: {data['demand']['demand_units'].sum():,} units")
