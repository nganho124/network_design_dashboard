"""
Synthetic data generator — Germany network (DIY / Home Improvement & Furniture Retail).

Structure: Supplier -> Warehouse (WH) -> Store, unit of measure = PALLET throughout.

Design choices:
- 30% of suppliers are international, carrying ~60% of total supply volume,
  with longer lead times than domestic suppliers.
- 8 warehouses spread across Germany (4 "Central" hubs in the biggest metros,
  4 "Regional" hubs); capacity sized from catchment demand, floored/capped
  around an even split, and rounded to the nearest 100 pallets.
- Store demand is population-weighted but regionally adjusted: the
  Rhine-Ruhr area around Cologne is deliberately thinned out (too many
  closely-packed candidate cities over-represented it), while Bavaria and
  Baden-Wuerttemberg are boosted.
- Product groups: fewer pure hardware/plumbing categories, several
  furniture categories (IKEA-style flat-pack / home furnishings) added.
- supply_baseline_share (Supplier x WH x Group) and delivery_baseline_share
  (WH x Store x Group) represent the FIXED baseline distribution — the
  "no action taken" scenario, mirroring the real Reece-style Branch
  Delivery Share / Supply Share datasets.
"""

import numpy as np
import pandas as pd

import db

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

# Map every candidate city to its respective German state
CITY_STATES = {
    "Hamburg": "Hamburg", "Berlin": "Berlin", "Munich": "Bavaria", "Cologne": "North Rhine-Westphalia",
    "Frankfurt": "Hesse", "Stuttgart": "Baden-Württemberg", "Leipzig": "Saxony", "Nuremberg": "Bavaria",
    "Dortmund": "North Rhine-Westphalia", "Essen": "North Rhine-Westphalia", "Dresden": "Saxony",
    "Hannover": "Lower Saxony", "Bremen": "Bremen", "Duisburg": "North Rhine-Westphalia",
    "Bochum": "North Rhine-Westphalia", "Wuppertal": "North Rhine-Westphalia",
    "Bielefeld": "North Rhine-Westphalia", "Bonn": "North Rhine-Westphalia", "Mannheim": "Baden-Württemberg",
    "Karlsruhe": "Baden-Württemberg", "Wiesbaden": "Hesse", "Muenster": "North Rhine-Westphalia",
    "Augsburg": "Bavaria", "Aachen": "North Rhine-Westphalia", "Moenchengladbach": "North Rhine-Westphalia",
    "Braunschweig": "Lower Saxony", "Chemnitz": "Saxony", "Kiel": "Schleswig-Holstein",
    "Halle": "Saxony-Anhalt", "Magdeburg": "Saxony-Anhalt", "Freiburg": "Baden-Württemberg",
    "Krefeld": "North Rhine-Westphalia", "Luebeck": "Schleswig-Holstein", "Oberhausen": "North Rhine-Westphalia",
    "Erfurt": "Thuringia", "Mainz": "Rhineland-Palatinate", "Rostock": "Mecklenburg-Vorpommern",
    "Kassel": "Hesse", "Saarbruecken": "Saarland", "Potsdam": "Brandenburg", "Herne": "North Rhine-Westphalia", 
    "Neuss": "North Rhine-Westphalia", "Paderborn": "North Rhine-Westphalia", "Regensburg": "Bavaria", 
    "Ingolstadt": "Bavaria", "Wuerzburg": "Bavaria", "Fuerth": "Bavaria", "Wolfsburg": "Lower Saxony", 
    "Offenbach": "Hesse", "Ulm": "Baden-Württemberg", "Heidelberg": "Baden-Württemberg", 
    "Pforzheim": "Baden-Württemberg", "Goettingen": "Lower Saxony", "Bottrop": "North Rhine-Westphalia", 
    "Trier": "Rhineland-Palatinate", "Recklinghausen": "North Rhine-Westphalia", "Reutlingen": "Baden-Württemberg", 
    "Bremerhaven": "Bremen", "Koblenz": "Rhineland-Palatinate", "Bergisch Gladbach": "North Rhine-Westphalia", 
    "Jena": "Thuringia", "Remscheid": "North Rhine-Westphalia", "Erlangen": "Bavaria", "Moers": "North Rhine-Westphalia", 
    "Salzgitter": "Lower Saxony", "Siegen": "North Rhine-Westphalia", "Hildesheim": "Lower Saxony", 
    "Cottbus": "Brandenburg", "Kaiserslautern": "Rhineland-Palatinate", "Guetersloh": "North Rhine-Westphalia", 
    "Witten": "North Rhine-Westphalia", "Iserlohn": "North Rhine-Westphalia", "Ratingen": "North Rhine-Westphalia", 
    "Hanau": "Hesse", "Zwickau": "Saxony", "Flensburg": "Schleswig-Holstein", "Schwerin": "Mecklenburg-Vorpommern",
    "Luenen": "North Rhine-Westphalia", "Villingen-Schwenningen": "Baden-Württemberg", "Konstanz": "Baden-Württemberg",
    "Worms": "Rhineland-Palatinate", "Marburg": "Hesse", "Neubrandenburg": "Mecklenburg-Vorpommern",
    "Detmold": "North Rhine-Westphalia", "Giessen": "Hesse", "Ludwigshafen": "Rhineland-Palatinate",
    "Offenburg": "Baden-Württemberg", "Ravensburg": "Baden-Württemberg", "Neumuenster": "Schleswig-Holstein",
    "Landshut": "Bavaria", "Celle": "Lower Saxony", "Delmenhorst": "Lower Saxony",
    "Lippstadt": "North Rhine-Westphalia", "Rheine": "North Rhine-Westphalia", "Dorsten": "North Rhine-Westphalia"
}


# dedupe defensive (in case of accidental repeats above)
_seen = set()
GERMAN_CITIES = [c for c in GERMAN_CITIES if not (c[0] in _seen or _seen.add(c[0]))]

# 8 warehouse hub cities — order matters: first 4 become "Central WH", rest "Regional WH"
WAREHOUSE_CITIES = [
    "Hamburg", "Berlin", "Munich", "Cologne",       # Central WH (biggest metros)
    "Frankfurt", "Stuttgart", "Leipzig", "Nuremberg",  # Regional WH
]
CENTRAL_WH_CITIES = {"Hamburg", "Berlin", "Munich", "Cologne"}

# Regional cost index (1.0 = national average) driving both fixed cost and
# handling cost. Reflects the general, well-known pattern in German
# commercial real-estate/labor markets: Bavaria/Baden-Wuerttemberg/Hesse run
# highest, Berlin near average, former East Germany (Leipzig) lowest.
# Approximate, illustrative — not sourced from a specific report.
REGIONAL_COST_INDEX = {
    "Munich": 1.35, "Stuttgart": 1.25, "Frankfurt": 1.20, "Hamburg": 1.15,
    "Cologne": 1.10, "Berlin": 1.00, "Nuremberg": 0.90, "Leipzig": 0.80,
}

# regional demand weighting: thin out the densely-packed Rhine-Ruhr area
# around Cologne, boost Bavaria and Baden-Wuerttemberg
COLOGNE_COORD = (50.9375, 6.9603)
COLOGNE_THIN_RADIUS_KM = 90
COLOGNE_THIN_MULTIPLIER = 0.45
BAVARIA_CITIES = {"Munich", "Nuremberg", "Augsburg", "Erlangen", "Fuerth",
                   "Regensburg", "Ingolstadt", "Wuerzburg", "Landshut"}
BW_CITIES = {"Stuttgart", "Heidelberg", "Karlsruhe", "Mannheim", "Ulm", "Reutlingen",
             "Pforzheim", "Freiburg", "Konstanz", "Villingen-Schwenningen",
             "Ravensburg", "Offenburg"}
BOOST_MULTIPLIER = 1.8

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

# Product groups: (group_id, category, weight_kg_per_pallet, unit_value_eur_per_pallet)
# Reduced pure hardware/plumbing categories (merged several), added furniture
# categories (flat-pack / home furnishings, IKEA-style) to diversify the mix.
PRODUCT_GROUPS_RAW = [
    ("PG01", "Power & Hand Tools",       350, 9000),
    ("PG02", "Fasteners & Fixings",      600, 3000),
    ("PG03", "Plumbing & Fittings",      450, 4500),
    ("PG04", "Electrical & Cabling",     400, 6000),
    ("PG05", "Paint & Coatings",         550, 3500),
    ("PG06", "Safety & Workwear",        250, 5000),
    ("PG07", "Adhesives & Sealants",     500, 3200),
    ("PG08", "Garden Equipment",         400, 7000),
    ("PG09", "Timber & Boards",          700, 2800),
    ("PG10", "Flooring Materials",       650, 3800),
    ("PG11", "Insulation Materials",     300, 2200),
    ("PG12", "Cleaning Supplies",        350, 1800),
    ("PG13", "Ladders & Access",         380, 4200),
    ("PG14", "Flat-Pack Furniture",      500, 8500),
    ("PG15", "Storage & Shelving",       450, 6500),
    ("PG16", "Kitchen & Cabinets",       600, 11000),
    ("PG17", "Home Decor & Textiles",    200, 4000),
    ("PG18", "Outdoor & Patio Furniture", 550, 9500),
]


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _round_hundred(x):
    return int(round(x / 100.0) * 100)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_product_groups() -> pd.DataFrame:
    return pd.DataFrame(PRODUCT_GROUPS_RAW, columns=[
        "group_id", "category", "weight_kg_per_pallet", "unit_value_eur_per_pallet",
    ])


def generate_warehouses() -> pd.DataFrame:
    city_lookup = {name: (lat, lon) for name, lat, lon, _ in GERMAN_CITIES}
    rows = []
    for i, city in enumerate(WAREHOUSE_CITIES, start=1):
        lat, lon = city_lookup[city]
        is_central = city in CENTRAL_WH_CITIES
        wh_name = f"{'Central' if is_central else 'Regional'} WH {city}"
        rows.append({
            "wh_id": f"WH{i:03d}", "wh_name": wh_name, "city": city, "lat": lat, "lon": lon,
            "regional_cost_index": REGIONAL_COST_INDEX.get(city, 1.0),
        })
    return pd.DataFrame(rows)


def _store_weight_multiplier(city_name: str, lat: float, lon: float) -> float:
    if city_name in BAVARIA_CITIES or city_name in BW_CITIES:
        return BOOST_MULTIPLIER
    if _haversine(lat, lon, *COLOGNE_COORD) < COLOGNE_THIN_RADIUS_KM:
        return COLOGNE_THIN_MULTIPLIER
    return 1.0


def generate_stores(product_groups: pd.DataFrame, n_stores: int = 400):
    """Returns (stores_df, demand_df). One store per sampled city, demand scaled by
    population — with a regional multiplier to thin out the Cologne/Rhine-Ruhr
    cluster and boost Bavaria / Baden-Wuerttemberg."""
    raw_weights = []
    for name, lat, lon, pop in GERMAN_CITIES:
        w = (pop ** 0.6) * _store_weight_multiplier(name, lat, lon)
        raw_weights.append(w)
    weights = np.array(raw_weights)
    weights = weights / weights.sum()

    idx = RNG.choice(len(GERMAN_CITIES), size=n_stores, replace=True, p=weights)

    stores = []
    demand_rows = []
    for i, city_idx in enumerate(idx, start=1):
        name, lat, lon, pop = GERMAN_CITIES[city_idx]
        state = CITY_STATES.get(name, "Unknown State") # Add state lookup here
        
        jlat, jlon = lat + RNG.uniform(-0.05, 0.05), lon + RNG.uniform(-0.05, 0.05)
        store_id = f"ST_{i:03d}_{name.upper()}"
        
        # Add the state to the stores dictionary
        stores.append({"store_id": store_id, "city": name, "state": state, "lat": jlat, "lon": jlon})

        base_demand = pop * RNG.uniform(0.45, 0.8)  
        for _, pg in product_groups.iterrows():
            demand_rows.append({
                "store_id": store_id, "group_id": pg["group_id"],
                "demand_pallets": max(1, int(base_demand * RNG.uniform(0.02, 0.06))),
            })

    return pd.DataFrame(stores), pd.DataFrame(demand_rows)


def generate_suppliers(n_suppliers: int = 20, intl_count_share: float = 0.30,
                        intl_volume_share: float = 0.60) -> pd.DataFrame:
    n_intl = max(1, round(n_suppliers * intl_count_share))
    n_dom = n_suppliers - n_intl

    intl_hubs = [INTL_SUPPLIER_HUBS[i % len(INTL_SUPPLIER_HUBS)] for i in range(n_intl)]
    dom_cities = [DOMESTIC_SUPPLIER_CITIES[i % len(DOMESTIC_SUPPLIER_CITIES)] for i in range(n_dom)]
    city_lookup = {name: (lat, lon) for name, lat, lon, _ in GERMAN_CITIES}

    intl_raw = RNG.dirichlet(np.ones(n_intl)) * intl_volume_share
    dom_raw = RNG.dirichlet(np.ones(n_dom)) * (1 - intl_volume_share)

    rows = []
    sid = 1
    for i, (name, country, lat, lon) in enumerate(intl_hubs):
        rows.append({
            "supplier_id": f"SUP_{sid:03d}", "name": f"{name} {i+1}", "country": country,
            "type": "international", "lat": lat, "lon": lon,
            "lead_time_days": int(RNG.uniform(25, 45)),
            "volume_share": round(float(intl_raw[i]), 4),
        })
        sid += 1
    for i, city in enumerate(dom_cities):
        lat, lon = city_lookup[city]
        rows.append({
            "supplier_id": f"SUP_{sid:03d}", "name": f"{city} Supplier", "country": "Germany",
            "type": "domestic", "lat": lat, "lon": lon,
            "lead_time_days": int(RNG.uniform(2, 7)),
            "volume_share": round(float(dom_raw[i]), 4),
        })
        sid += 1

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
    """Capacity = nearest-catchment demand * buffer, floored/capped relative to an
    even split (so no single metro starves the others), then rounded to the
    nearest 100 pallets."""
    nearest = assign_stores_to_nearest_wh(stores, warehouses).reset_index()
    demand_with_wh = demand.merge(nearest, on="store_id")
    cap_by_wh = demand_with_wh.groupby("nearest_wh_id")["demand_pallets"].sum() * buffer

    n_wh = len(warehouses)
    even_split = demand["demand_pallets"].sum() * buffer / n_wh
    floor, ceiling = even_split * min_ratio, even_split * max_ratio

    warehouses = warehouses.copy()
    raw_cap = warehouses["wh_id"].map(cap_by_wh).fillna(0)
    clipped = raw_cap.clip(lower=floor, upper=ceiling)
    warehouses["capacity_pallets"] = clipped.apply(_round_hundred).astype(int)
    return warehouses


def compute_warehouse_costs(warehouses: pd.DataFrame, rent_eur_per_pallet: float = 6.0,
                             base_overhead_eur: float = 18_000.0,
                             handling_base_eur: float = 10.0) -> pd.DataFrame:
    """
    Fixed cost and handling cost, both grounded in two real drivers instead
    of pure randomness:
      - warehouse SIZE (capacity_pallets) — a bigger footprint costs more
        in rent and staffing, regardless of city
      - REGIONAL cost index — rent and labor both scale with local cost of
        living/commercial real estate

    fixed_cost = (rent per pallet slot * capacity + base overhead) * regional index
    handling_cost = base handling rate * regional index (labor-cost driven,
        largely independent of warehouse size)

    This is what keeps a small warehouse in a cheap region (e.g. Leipzig)
    cheaper than a large one in an expensive region (e.g. Munich), and a
    large warehouse in an average-cost region (e.g. Berlin) priced between
    the two — rather than fixed cost being unrelated to size or location.
    """
    warehouses = warehouses.copy()
    idx = warehouses["regional_cost_index"]
    cap = warehouses["capacity_pallets"]

    fixed_raw = (cap * rent_eur_per_pallet + base_overhead_eur) * idx
    fixed_raw = fixed_raw * RNG.uniform(0.95, 1.05, size=len(warehouses))  # small realistic noise
    warehouses["fixed_cost_eur_per_month"] = fixed_raw.apply(_round_hundred).astype(int)

    handling_raw = handling_base_eur * idx * RNG.uniform(0.85, 1.15, size=len(warehouses))
    warehouses["handling_cost_eur_pallet"] = handling_raw.round(2)

    return warehouses


def compute_inbound_transport_cost(suppliers: pd.DataFrame, warehouses: pd.DataFrame) -> pd.DataFrame:
    """Cost per pallet, supplier -> each WH. International adds a flat
    ocean-freight/customs base fee reflecting real per-pallet import economics."""
    rows = []
    for _, sup in suppliers.iterrows():
        for _, wh in warehouses.iterrows():
            dist_km = _haversine(sup["lat"], sup["lon"], wh["lat"], wh["lon"])
            if sup["type"] == "international":
                # ocean freight economizes over distance — base covers the sea leg,
                # only a modest per-km term for inland/customs variance
                cost = 150 + 0.01 * dist_km
            else:
                cost = 15 + 0.15 * dist_km    # domestic trucking, per pallet
            rows.append({"supplier_id": sup["supplier_id"], "wh_id": wh["wh_id"],
                        "distance_km": round(dist_km, 1), "cost_per_pallet_eur": round(cost, 2),
                        "lead_time_days": sup["lead_time_days"]})
    return pd.DataFrame(rows)


def compute_delivery_cost(warehouses: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    """Cost per pallet, WH -> store (last-mile distribution)."""
    rows = []
    for _, wh in warehouses.iterrows():
        for _, s in stores.iterrows():
            dist_km = _haversine(wh["lat"], wh["lon"], s["lat"], s["lon"])
            cost = 15 + 0.12 * dist_km
            days = round(dist_km / 550 + 0.4, 2)
            rows.append({"wh_id": wh["wh_id"], "store_id": s["store_id"],
                        "distance_km": round(dist_km, 1), "cost_per_pallet_eur": round(cost, 2),
                        "days_to_serve": days})
    return pd.DataFrame(rows)


def generate_supply_baseline_share(suppliers: pd.DataFrame, product_groups: pd.DataFrame,
                                    warehouses: pd.DataFrame, inbound_cost: pd.DataFrame,
                                    suppliers_per_group: int = 3) -> pd.DataFrame:
    """Baseline fixed Supplier -> WH -> Group volume share (mirrors the real
    'Supply Share' dataset). Suppliers are picked per (WH, group) weighted by
    their overall volume_share AND proximity to that warehouse, so nearby
    suppliers are more likely to feature in that WH's baseline mix."""
    cost_lookup = inbound_cost.set_index(["wh_id", "supplier_id"])["distance_km"]
    rows = []
    for _, wh in warehouses.iterrows():
        for _, pg in product_groups.iterrows():
            dists = suppliers["supplier_id"].map(lambda sid: cost_lookup.get((wh["wh_id"], sid), np.nan))
            dists = dists.fillna(dists.mean())
            proximity_weight = 1.0 / (dists.values + 50)
            combined = suppliers["volume_share"].values * proximity_weight
            combined = combined / combined.sum()

            n_pick = min(suppliers_per_group, len(suppliers))
            chosen_idx = RNG.choice(len(suppliers), size=n_pick, replace=False, p=combined)
            chosen = suppliers.iloc[chosen_idx]
            raw_shares = RNG.dirichlet(np.ones(n_pick))
            # round all but the last share, then derive the last so the group sums to exactly 1.0
            shares = [round(float(s), 3) for s in raw_shares[:-1]]
            shares.append(round(1 - sum(shares), 3))
            for (_, sup), share in zip(chosen.iterrows(), shares):
                rows.append({"supplier_id": sup["supplier_id"], "wh_id": wh["wh_id"],
                            "group_id": pg["group_id"], "volume_share": share})
    return pd.DataFrame(rows)


def generate_delivery_baseline_share(stores: pd.DataFrame, warehouses: pd.DataFrame,
                                      product_groups: pd.DataFrame,
                                      primary_share_range=(0.85, 1.0)) -> pd.DataFrame:
    """Baseline fixed WH -> Store -> Group volume share (mirrors the real
    'Branch Delivery Share' dataset). Each store is served mostly by its
    nearest WH, with a small residual share to the second-nearest WH to
    reflect realistic occasional cross-shipping."""
    rows = []
    for _, s in stores.iterrows():
        dists = warehouses.apply(lambda w: _haversine(s["lat"], s["lon"], w["lat"], w["lon"]), axis=1)
        order = dists.sort_values().index.tolist()
        primary_wh = warehouses.loc[order[0], "wh_id"]
        secondary_wh = warehouses.loc[order[1], "wh_id"] if len(order) > 1 else None

        primary_share = round(float(RNG.uniform(*primary_share_range)), 3)
        if primary_share >= 0.999:
            primary_share, secondary_wh = 1.0, None
        else:
            secondary_share = round(1 - primary_share, 3)

        for _, pg in product_groups.iterrows():
            rows.append({"wh_id": primary_wh, "store_id": s["store_id"],
                        "group_id": pg["group_id"], "volume_share": primary_share})
            if secondary_wh is not None:
                rows.append({"wh_id": secondary_wh, "store_id": s["store_id"],
                            "group_id": pg["group_id"], "volume_share": secondary_share})
    return pd.DataFrame(rows)


def generate_supply_share(suppliers: pd.DataFrame, delivery_baseline_share: pd.DataFrame,
                           demand: pd.DataFrame, supply_baseline_share: pd.DataFrame,
                           extra_suppliers_per_group: int = 2,
                           extra_share_total: float = 0.08) -> pd.DataFrame:
    """Scenario-facing sourcing eligibility: each supplier's share of a product
    group's TOTAL network volume (Supplier x Group, no wh_id) — used by the
    solver as a network-wide sourcing cap when testing open/close scenarios,
    instead of the fixed per-warehouse supply_baseline_share split.

    Derived from the baseline mix, then "widened": a couple of eligible-but-
    unused suppliers per group are added with a modest share, mirroring how a
    real Approved Supplier List is broader than what's actually flowing today
    — without that, a what-if scenario would have no real sourcing flexibility
    to explore beyond what's already used in the baseline."""
    wg = delivery_baseline_share.merge(demand, on=["store_id", "group_id"])
    wg["pallets"] = wg["volume_share"] * wg["demand_pallets"]
    wh_group_volume = wg.groupby(["wh_id", "group_id"])["pallets"].sum().rename("wh_group_pallets").reset_index()

    merged = supply_baseline_share.merge(wh_group_volume, on=["wh_id", "group_id"])
    merged["weighted_pallets"] = merged["volume_share"] * merged["wh_group_pallets"]
    supplier_group_pallets = merged.groupby(["supplier_id", "group_id"])["weighted_pallets"].sum()

    rows = []
    for group_id, pallets in supplier_group_pallets.groupby(level="group_id"):
        pallets = pallets.droplevel("group_id")
        base_share = pallets / pallets.sum()

        candidates = suppliers[~suppliers["supplier_id"].isin(base_share.index)]
        n_extra = min(extra_suppliers_per_group, len(candidates))
        combined = base_share * (1 - extra_share_total)

        if n_extra > 0:
            weights = candidates["volume_share"].to_numpy()
            weights = weights / weights.sum()
            chosen_idx = RNG.choice(len(candidates), size=n_extra, replace=False, p=weights)
            chosen_ids = candidates.iloc[chosen_idx]["supplier_id"].tolist()
            extra_shares = RNG.dirichlet(np.ones(n_extra)) * extra_share_total
            for sid, share in zip(chosen_ids, extra_shares):
                combined[sid] = share
        else:
            combined = combined / combined.sum()  # no room to widen, renormalize back to 1.0

        for supplier_id, share in combined.items():
            rows.append({"supplier_id": supplier_id, "group_id": group_id, "volume_share": round(float(share), 4)})

    return pd.DataFrame(rows)


# stepped import pricing: (min_pallets, max_pallets) per tier, and a cost
# multiplier relative to the flat international rate in inbound_cost —
# models consolidation savings (LCL vs FCL-style container economics)
INBOUND_TIERS = [
    {"tier_id": 1, "min_pallets": 0, "max_pallets": 19, "multiplier": 1.35},
    {"tier_id": 2, "min_pallets": 20, "max_pallets": 39, "multiplier": 1.00},
    {"tier_id": 3, "min_pallets": 40, "max_pallets": None, "multiplier": 0.75},
]


def compute_inbound_cost_tiers(suppliers: pd.DataFrame, warehouses: pd.DataFrame,
                                inbound_cost: pd.DataFrame) -> pd.DataFrame:
    """Stepped per-pallet import cost, INTERNATIONAL suppliers only — small
    shipments pay a premium, large ones get a volume discount, so a scenario
    that consolidates import volume onto fewer (supplier, WH) shipments and
    redistributes via internal transfer can trade a cheaper import rate
    against transfer_cost + extra handling. Domestic suppliers keep the flat
    inbound_cost rate — short-haul trucking doesn't have the same step
    economics as ocean freight/customs consolidation."""
    intl = suppliers[suppliers["type"] == "international"]
    flat_rate = inbound_cost.set_index(["supplier_id", "wh_id"])["cost_per_pallet_eur"]

    rows = []
    for _, sup in intl.iterrows():
        for _, wh in warehouses.iterrows():
            base_rate = flat_rate.get((sup["supplier_id"], wh["wh_id"]))
            for tier in INBOUND_TIERS:
                rows.append({
                    "supplier_id": sup["supplier_id"], "wh_id": wh["wh_id"], "tier_id": tier["tier_id"],
                    "min_pallets": tier["min_pallets"], "max_pallets": tier["max_pallets"],
                    "cost_per_pallet_eur": round(base_rate * tier["multiplier"], 2),
                })
    return pd.DataFrame(rows)


def compute_transfer_cost(warehouses: pd.DataFrame, rate_eur_per_km_pallet: float = 0.10,
                           base_fee_eur: float = 8.0) -> pd.DataFrame:
    """WH -> WH internal transfer cost (inter-hub trucking), used when a
    scenario consolidates import volume at one WH and redistributes it to
    others rather than importing directly into each."""
    rows = []
    for _, a in warehouses.iterrows():
        for _, b in warehouses.iterrows():
            if a["wh_id"] == b["wh_id"]:
                continue
            dist_km = _haversine(a["lat"], a["lon"], b["lat"], b["lon"])
            cost = base_fee_eur + rate_eur_per_km_pallet * dist_km
            days = round(dist_km / 550 + 0.3, 2)
            rows.append({"wh_id_from": a["wh_id"], "wh_id_to": b["wh_id"],
                        "distance_km": round(dist_km, 1), "cost_per_pallet_eur": round(cost, 2),
                        "days": days})
    return pd.DataFrame(rows)


def build_all_data(n_stores: int = 400, n_suppliers: int = 20):
    product_groups = generate_product_groups()
    warehouses = generate_warehouses()
    stores, demand = generate_stores(product_groups, n_stores=n_stores)
    warehouses = size_warehouse_capacity(warehouses, stores, demand)
    warehouses = compute_warehouse_costs(warehouses)
    suppliers = generate_suppliers(n_suppliers=n_suppliers)
    inbound_cost = compute_inbound_transport_cost(suppliers, warehouses)
    delivery_cost = compute_delivery_cost(warehouses, stores)
    supply_baseline_share = generate_supply_baseline_share(suppliers, product_groups, warehouses, inbound_cost)
    delivery_baseline_share = generate_delivery_baseline_share(stores, warehouses, product_groups)
    supply_share = generate_supply_share(suppliers, delivery_baseline_share, demand, supply_baseline_share)
    inbound_cost_tiers = compute_inbound_cost_tiers(suppliers, warehouses, inbound_cost)
    transfer_cost = compute_transfer_cost(warehouses)

    return {
        "product_groups": product_groups,
        "warehouses": warehouses,
        "stores": stores,
        "demand": demand,
        "suppliers": suppliers,
        "inbound_cost": inbound_cost,
        "delivery_cost": delivery_cost,
        "supply_baseline_share": supply_baseline_share,
        "delivery_baseline_share": delivery_baseline_share,
        "supply_share": supply_share,
        "inbound_cost_tiers": inbound_cost_tiers,
        "transfer_cost": transfer_cost,
    }


if __name__ == "__main__":
    data = build_all_data()
    for name, df in data.items():
        print(f"\n=== {name} ({len(df)} rows) ===")
        print(df.head(4).to_string(index=False))

    print("\n--- Validation ---")
    wh = data["warehouses"]
    print(wh[["wh_id", "wh_name", "regional_cost_index", "capacity_pallets",
               "fixed_cost_eur_per_month", "handling_cost_eur_pallet"]]
          .sort_values("capacity_pallets", ascending=False).to_string(index=False))
    print(f"Max/min capacity ratio: {wh['capacity_pallets'].max() / wh['capacity_pallets'].min():.1f}x")
    print(f"Fixed cost vs capacity correlation: {wh['fixed_cost_eur_per_month'].corr(wh['capacity_pallets']):.2f}")
    print(f"Handling cost vs regional index correlation: "
          f"{wh['handling_cost_eur_pallet'].corr(wh['regional_cost_index']):.2f}")

    stores = data["stores"]
    cologne_area = stores.apply(
        lambda r: _haversine(r["lat"], r["lon"], *COLOGNE_COORD) < COLOGNE_THIN_RADIUS_KM, axis=1).sum()
    bavaria_bw = stores["city"].isin(BAVARIA_CITIES | BW_CITIES).sum()
    print(f"Stores near Cologne (<{COLOGNE_THIN_RADIUS_KM}km): {cologne_area} / {len(stores)}")
    print(f"Stores in Bavaria/Baden-Wuerttemberg cities: {bavaria_bw} / {len(stores)}")

    intl_vol = data["suppliers"].loc[data["suppliers"]["type"] == "international", "volume_share"].sum()
    print(f"Intl supplier count share: {(data['suppliers']['type'] == 'international').mean():.0%}")
    print(f"Intl supplier volume share: {intl_vol:.0%}")
    print(f"Supplier IDs: {data['suppliers']['supplier_id'].tolist()}")

    sbs = data["supply_baseline_share"]
    check = sbs.groupby(["wh_id", "group_id"])["volume_share"].sum().round(3)
    print(f"supply_baseline_share sums to 1.0 per (wh,group)? {(check == 1.0).all()}")

    dbs = data["delivery_baseline_share"]
    check2 = dbs.groupby(["store_id", "group_id"])["volume_share"].sum().round(3)
    print(f"delivery_baseline_share sums to 1.0 per (store,group)? {(check2 == 1.0).all()}")

    ss = data["supply_share"]
    check3 = ss.groupby("group_id")["volume_share"].sum().round(3)
    print(f"supply_share sums to 1.0 per group? {(check3 == 1.0).all()}")
    avg_suppliers_per_group = ss.groupby("group_id")["supplier_id"].nunique().mean()
    print(f"Avg eligible suppliers per group in supply_share: {avg_suppliers_per_group:.1f} "
          f"(vs {sbs.groupby('group_id')['supplier_id'].nunique().mean():.1f} used across baseline WH mix)")

    ict = data["inbound_cost_tiers"]
    print(f"inbound_cost_tiers rows: {len(ict)} "
          f"({ict['supplier_id'].nunique()} intl suppliers x {ict['wh_id'].nunique()} WH x 3 tiers)")

    tc = data["transfer_cost"]
    print(f"transfer_cost rows: {len(tc)} (should be n_wh*(n_wh-1) = "
          f"{len(data['warehouses']) * (len(data['warehouses']) - 1)})")

    print("\n--- Saving to reference data ---")
    db.init_storage()
    db.save_reference_data(data)
    print(f"Saved {len(data)} tables to {db.REFERENCE_DIR}/")