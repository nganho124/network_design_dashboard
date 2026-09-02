"""
Scenario schema + session_state helpers.

This is the ONE data contract every part of the app reads/writes through:
- map_view.py reads scenario + reference data (+ results, once solver.py
  is rewritten) to draw the network
- dashboard_view.py reads results to draw charts (still on the OLD schema —
  not yet updated for the warehouse/store/pallet model, see solver.py note)
- (hackathon night) the AI chat writes updates into scenario via update_scenario()

Reference data (warehouses, stores, demand, suppliers, cost curves, baseline
shares) comes from db.load_reference_data() — the parquet files produced by
generate_germany_data.py. Nothing here regenerates data; it only loads what's
already on disk.
"""

import streamlit as st
import db


def init_session_state():
    """Call once at the top of app.py"""
    if "scenario" not in st.session_state:
        ref = db.load_reference_data()

        st.session_state.warehouses = ref["warehouses"]
        st.session_state.stores = ref["stores"]
        st.session_state.demand = ref["demand"]
        st.session_state.product_groups = ref["product_groups"]
        st.session_state.suppliers = ref["suppliers"]
        st.session_state.inbound_cost = ref["inbound_cost"]
        st.session_state.delivery_cost = ref["delivery_cost"]
        st.session_state.supply_baseline_share = ref["supply_baseline_share"]
        st.session_state.delivery_baseline_share = ref["delivery_baseline_share"]

        st.session_state.scenario = {
            # dict: wh_id -> "open" | "closed"
            "wh_status": {wh_id: "open" for wh_id in ref["warehouses"]["wh_id"]},
        }
        st.session_state.results = None        # filled in once solver.py is rewritten for this schema
        st.session_state.chat_history = []      # populated once AI chat is added


def update_scenario(patch: dict):
    """
    Merge a partial update into the scenario.
    This is the single entry point both manual UI controls AND
    the future AI chat parser should call — never mutate
    st.session_state.scenario directly from elsewhere.
    """
    for key, value in patch.items():
        if key in st.session_state.scenario and isinstance(value, dict):
            st.session_state.scenario[key].update(value)
        else:
            st.session_state.scenario[key] = value


def get_scenario_schema_for_llm() -> dict:
    """
    Human/LLM-readable description of the scenario shape.
    Reuse this directly as (or to build) the Claude tool-use input_schema
    on hackathon night — keep it in sync with the dict above.
    """
    return {
        "wh_status": "object mapping wh_id (e.g. 'WH001') -> 'open' or 'closed'",
    }


def get_baseline_flows() -> "pd.DataFrame":
    """
    WH -> Store pallet flow, derived from delivery_baseline_share x demand,
    filtered to currently-open warehouses.

    This is a STAND-IN for solver output: it shows what the baseline (fixed
    share) network looks like, and reacts to opening/closing a warehouse by
    dropping that warehouse's flows — but it does NOT reallocate a closed
    warehouse's demand to another one (that requires solver.py, which still
    targets the old DC/region schema and hasn't been rewritten for the
    warehouse/store/pallet model yet). Once solver.py is updated, map_view.py
    should prefer st.session_state.results over this function whenever a
    scenario has actually been solved.
    """
    dbs = st.session_state.delivery_baseline_share
    demand = st.session_state.demand
    open_wh = {wh for wh, status in st.session_state.scenario["wh_status"].items() if status == "open"}

    merged = dbs.merge(demand, on=["store_id", "group_id"])
    merged["pallets"] = merged["volume_share"] * merged["demand_pallets"]
    merged = merged[merged["wh_id"].isin(open_wh)]

    return merged.groupby(["wh_id", "store_id"], as_index=False)["pallets"].sum()