"""
Scenario schema + session_state helpers.

This is the ONE data contract every part of the app reads/writes through:
- map_view.py reads scenario + results to draw the network
- dashboard_view.py reads results to draw charts
- (hackathon night) the AI chat writes updates into scenario via update_scenario()

Keeping this schema simple and flat makes it trivial to turn into a
Claude tool-use / function-calling JSON schema later.
"""

import streamlit as st
from data import load_sample_data


def init_session_state():
    """Call once at the top of app.py"""
    if "scenario" not in st.session_state:
        dcs, demand, distance = load_sample_data()
        st.session_state.scenario = {
            # dict: dc_id -> "open" | "closed"
            "dc_status": {dc_id: "open" for dc_id in dcs["dc_id"]},
            # dict: region_id -> "direct" | "lsp"  (delivery / distribution mode)
            "delivery_mode": {r: "direct" for r in demand["region_id"]},
        }
        st.session_state.dcs = dcs            # static reference data (lat/lon/capacity/cost)
        st.session_state.demand = demand       # static reference data (region demand)
        st.session_state.distance = distance   # static reference data (dc x region distance/cost)
        st.session_state.results = None        # filled in by solver.solve_network()
        st.session_state.chat_history = []     # populated once AI chat is added


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
        "dc_status": "object mapping dc_id -> 'open' or 'closed'",
        "delivery_mode": "object mapping region_id -> 'direct' (ship from DC to store) "
                          "or 'lsp' (sell to logistics service provider, they distribute)",
    }
