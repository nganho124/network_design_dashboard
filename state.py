"""
Scenario schema + session_state helpers.

This is the ONE data contract every part of the app reads/writes through:
- map_view.py reads scenario + reference data + results (solver.py output,
  or a scenario loaded from the library) to draw the network
- dashboard_view.py reads results to draw charts (still on its own fixed-share
  approximation, not yet wired to solve_network() — see helper_calculation.py)
- app.py's scenario library sidebar solves/saves scenarios and lets you pick
  a saved one, writing scenario + results back through this module
- app.py's scenario chat (chat_assistant.py) writes updates into scenario via
  update_scenario() too, same as the manual warehouse toggles

Reference data (warehouses, stores, demand, suppliers, cost curves, baseline
shares) comes from db.load_reference_data() — the parquet files produced by
generate_germany_data.py. Nothing here regenerates data; it only loads what's
already on disk.
"""

import streamlit as st
import db

# every table db.load_reference_data() must supply — kept as one list so a browser
# tab that's been open since before a table existed can self-heal (see below)
# instead of crashing with "st.session_state has no attribute ...".
REFERENCE_KEYS = [
    "warehouses", "stores", "demand", "product_groups", "suppliers",
    "inbound_cost", "delivery_cost", "supply_baseline_share", "delivery_baseline_share",
    # scenario-facing sourcing/consolidation inputs (see solver.py) — distinct
    # from the fixed supply_baseline_share used for the "no action taken" view
    "supply_share", "inbound_cost_tiers", "transfer_cost",
    # candidate-city pool + per-state cost basis for adding a brand-new ("greenfield")
    # warehouse to a scenario — see greenfield.py
    "city_directory", "state_cost_index",
]


def init_session_state():
    """Call once at the top of app.py"""
    if "scenario" not in st.session_state:
        ref = db.load_reference_data()
        for key in REFERENCE_KEYS:
            st.session_state[key] = ref[key]

        st.session_state.scenario = {
            # dict: wh_id -> "open" | "closed"
            "wh_status": {wh_id: "open" for wh_id in ref["warehouses"]["wh_id"]},
            # list of {"store_id", "group_id" (or "ALL"), "wh_id", "volume_share"} rows —
            # pins that (store, group) demand to specific warehouse(s) instead of leaving
            # it fully open to the solver. See update_scenario() for upsert/unpin rules
            # and solver.py's _resolve_forced_allocation() for how it's applied.
            "forced_allocation": [],
            # list of {"wh_id", "wh_name", "city"} rows — brand-new, not-yet-built
            # warehouses this scenario is testing (see greenfield.py). Scenario-only:
            # never written to the reference parquet, regenerated on the fly each
            # solve from city + state_cost_index. wh_status still governs open/closed
            # for these ids exactly like any other warehouse.
            "new_warehouses": [],
        }
        st.session_state.results = None        # solve_network() output, or a loaded saved scenario's
        st.session_state.chat_history = []      # populated once AI chat is added

    # keys added after the initial release: a browser tab already open when one of
    # these was introduced has "scenario" in session_state already, so the block
    # above is skipped and the key would otherwise never get set — self-heal here
    # instead of crashing on next rerun.
    missing_ref_keys = [k for k in REFERENCE_KEYS if k not in st.session_state]
    if missing_ref_keys:
        ref = db.load_reference_data()
        for key in missing_ref_keys:
            st.session_state[key] = ref[key]

    if "active_scenario_id" not in st.session_state:
        st.session_state.active_scenario_id = None  # scenario_id if `results` came from the library, else None (live/unsaved)

    st.session_state.scenario.setdefault("forced_allocation", [])  # ditto, for scenarios saved before this existed
    st.session_state.scenario.setdefault("new_warehouses", [])


def update_scenario(patch: dict):
    """
    Merge a partial update into the scenario.
    This is the single entry point both manual UI controls AND
    the AI chat (chat_assistant.py) should call — never mutate
    st.session_state.scenario directly from elsewhere.

    "forced_allocation" gets upsert/unpin semantics instead of a plain merge:
    patch["forced_allocation"] is a list of rows, each replacing any existing
    pin(s) for the same (store_id, group_id) — a row with wh_id=None removes
    the pin without adding a new one. This lets a single patch also express a
    multi-warehouse split (e.g. 70%/30%) without the rows clobbering each other.

    "new_warehouses" is upserted by wh_id the same way — a row with city=None
    removes that greenfield warehouse (and you should also close it via
    wh_status in the same patch, since removing it here doesn't do that).

    Any edit invalidates whatever `results` is currently loaded (a prior
    solve, or a scenario picked from the library) — it no longer corresponds
    to the edited scenario, so drop back to "live/unsaved" until re-solved.
    """
    for key, value in patch.items():
        if key == "forced_allocation":
            current = st.session_state.scenario.setdefault("forced_allocation", [])
            replaced_keys = {(row["store_id"], row["group_id"]) for row in value}
            current[:] = [row for row in current if (row["store_id"], row["group_id"]) not in replaced_keys]
            current.extend(row for row in value if row.get("wh_id") is not None)
        elif key == "new_warehouses":
            current = st.session_state.scenario.setdefault("new_warehouses", [])
            replaced_ids = {row["wh_id"] for row in value}
            current[:] = [row for row in current if row["wh_id"] not in replaced_ids]
            current.extend(row for row in value if row.get("city") is not None)
        elif key in st.session_state.scenario and isinstance(value, dict):
            st.session_state.scenario[key].update(value)
        else:
            st.session_state.scenario[key] = value
    st.session_state.results = None
    st.session_state.active_scenario_id = None


def next_new_warehouse_id(existing_ids: set) -> str:
    """Next unused 'WHNxx' id, given every id already in use (existing warehouses
    + already-added greenfield ones). Pure — shared by app.py's manual "Add
    warehouse" form and chat_assistant.py's open_new_warehouse tool, so both
    use the same numbering scheme."""
    return next(f"WHN{i:02d}" for i in range(1, 100) if f"WHN{i:02d}" not in existing_ids)


def get_effective_warehouses() -> "pd.DataFrame":
    """
    st.session_state.warehouses plus a row for each greenfield site in
    scenario["new_warehouses"] — cheap (no distance-cost computation), for
    anything that just needs warehouse rows: map markers, warehouse-status
    toggles, dashboards. solve_network() needs the full delivery/inbound/
    transfer cost tables too — see app.py's _effective_reference_tables(),
    which builds this same combined warehouse set alongside those.
    """
    import pandas as pd
    import greenfield

    warehouses = st.session_state.warehouses
    new_whs = st.session_state.scenario.get("new_warehouses", [])
    if not new_whs:
        return warehouses

    rows = [greenfield.resolve_warehouse_row(
        nw["city"], nw["wh_id"], nw["wh_name"],
        city_directory=st.session_state.city_directory, state_cost_index=st.session_state.state_cost_index,
    ) for nw in new_whs]
    return pd.concat([warehouses, pd.DataFrame(rows)], ignore_index=True)


def get_baseline_flows() -> "pd.DataFrame":
    """
    WH -> Store pallet flow, derived from delivery_baseline_share x demand,
    filtered to currently-open warehouses.

    This is a STAND-IN for solver output: it shows what the baseline (fixed
    share) network looks like, and reacts to opening/closing a warehouse by
    dropping that warehouse's flows — but it does NOT reallocate a closed
    warehouse's demand to another one. map_view.py prefers
    st.session_state.results (solve_network() output, or a loaded saved
    scenario) over this function whenever a scenario has actually been solved.
    """
    dbs = st.session_state.delivery_baseline_share
    demand = st.session_state.demand
    open_wh = {wh for wh, status in st.session_state.scenario["wh_status"].items() if status == "open"}

    merged = dbs.merge(demand, on=["store_id", "group_id"])
    merged["pallets"] = merged["volume_share"] * merged["demand_pallets"]
    merged = merged[merged["wh_id"].isin(open_wh)]

    return merged.groupby(["wh_id", "store_id"], as_index=False)["pallets"].sum()