"""
On-the-fly cost/geometry generation for a NOT-YET-BUILT ("greenfield")
warehouse a scenario adds at a city of the user's choosing — e.g. via chat
("open a new warehouse in Frankfurt") or a manual "Add warehouse" control.

Reuses the exact same cost-formula functions generate_germany_data.py uses
for the original 8 warehouses (compute_delivery_cost, compute_inbound_
transport_cost, compute_transfer_cost, compute_inbound_cost_tiers) — applied
ad hoc against a one-row warehouse DataFrame for the new site, against the
CURRENT store/supplier/warehouse sets. Nothing here touches
data/reference/*.parquet: a greenfield site is scenario-specific ("what if
we built here"), not part of "today's known network" — see state.py's
scenario docstring and REFERENCE_KEYS.

Unlike an existing warehouse, a greenfield site has no pre-set capacity or
sunk fixed cost — see solver.py, which treats a NaN capacity_pallets as
"uncapped" and instead charges capacity_rent_eur_per_pallet against whatever
throughput the solver actually routes there, plus a flat
base_overhead_eur_per_month. Both scale with the destination city's STATE
cost index (state_cost_index), since we don't have a hand-picked per-city
index the way the original 8 hub cities do.
"""

import pandas as pd

from generate_germany_data import (
    compute_delivery_cost,
    compute_inbound_cost_tiers,
    compute_inbound_transport_cost,
    compute_transfer_cost,
)


def resolve_warehouse_row(city: str, wh_id: str, wh_name: str, *, city_directory: pd.DataFrame,
                           state_cost_index: pd.DataFrame, rent_eur_per_pallet: float = 6.0,
                           base_overhead_eur: float = 18_000.0, handling_base_eur: float = 10.0) -> dict:
    """
    Just the warehouse row (location + state-driven cost basis) — no distance
    costs to every store/supplier, so it's cheap enough to call on every
    Streamlit rerun (e.g. map_view.py rendering warehouse markers). Use
    build_new_warehouse() instead when you also need the delivery/inbound/
    transfer cost tables for solving.

    Raises ValueError if `city` isn't in city_directory.
    """
    match = city_directory[city_directory["city"].str.lower() == city.strip().lower()]
    if match.empty:
        raise ValueError(f"'{city}' isn't in the known city directory.")
    site = match.iloc[0]

    idx_match = state_cost_index[state_cost_index["state"] == site["state"]]
    regional_cost_index = float(idx_match["regional_cost_index"].iloc[0]) if not idx_match.empty else 1.0

    return {
        "wh_id": wh_id, "wh_name": wh_name, "city": site["city"],
        "lat": site["lat"], "lon": site["lon"], "regional_cost_index": regional_cost_index,
        "capacity_pallets": None,          # no hard cap — a not-yet-built site is sized to demand
        "fixed_cost_eur_per_month": None,  # not a sunk cost — see the two fields below instead
        "capacity_rent_eur_per_pallet": round(rent_eur_per_pallet * regional_cost_index, 4),
        "base_overhead_eur_per_month": round(base_overhead_eur * regional_cost_index, 2),
        "handling_cost_eur_pallet": round(handling_base_eur * regional_cost_index, 2),
        "is_greenfield": True,
    }


def build_new_warehouse(city: str, wh_id: str, wh_name: str, *, city_directory: pd.DataFrame,
                         state_cost_index: pd.DataFrame, stores: pd.DataFrame,
                         suppliers: pd.DataFrame, warehouses: pd.DataFrame, **row_kwargs) -> dict:
    """
    Returns {"warehouse_row": dict, "delivery_cost": df, "inbound_cost": df,
    "transfer_cost": df, "inbound_cost_tiers": df} for the new site. Concatenate
    these onto the existing reference tables before calling solve_network() —
    see app.py's _effective_reference_tables().

    `warehouses` should be the full set of warehouses the new site needs
    transfer_cost pairs against (existing ones, plus any other greenfield
    sites already added this scenario) — the returned transfer_cost only
    contains rows involving the new wh_id, not pairs among `warehouses` itself
    (those are already known).

    Raises ValueError if `city` isn't in city_directory, or wh_id collides
    with an existing warehouse.
    """
    if wh_id in set(warehouses["wh_id"]):
        raise ValueError(f"Warehouse id '{wh_id}' is already in use.")
    warehouse_row = resolve_warehouse_row(city, wh_id, wh_name, city_directory=city_directory,
                                           state_cost_index=state_cost_index, **row_kwargs)
    new_wh_df = pd.DataFrame([warehouse_row])

    delivery_cost = compute_delivery_cost(new_wh_df, stores)
    inbound_cost = compute_inbound_transport_cost(suppliers, new_wh_df)
    inbound_cost_tiers = compute_inbound_cost_tiers(suppliers, new_wh_df, inbound_cost)

    all_wh = pd.concat([warehouses[["wh_id", "lat", "lon"]], new_wh_df[["wh_id", "lat", "lon"]]],
                        ignore_index=True)
    transfer_cost = compute_transfer_cost(all_wh)
    transfer_cost = transfer_cost[(transfer_cost["wh_id_from"] == wh_id) | (transfer_cost["wh_id_to"] == wh_id)]

    return {
        "warehouse_row": warehouse_row,
        "delivery_cost": delivery_cost,
        "inbound_cost": inbound_cost,
        "transfer_cost": transfer_cost,
        "inbound_cost_tiers": inbound_cost_tiers,
    }