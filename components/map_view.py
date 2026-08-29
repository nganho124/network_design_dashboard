"""
Tab 1: Network map.

Reads from st.session_state.scenario / dcs / demand / results ONLY.
Writes back to scenario via state.update_scenario() when the user
toggles a DC's status — never touches session_state directly.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
from state import update_scenario


def render_map_tab():
    st.subheader("Supply Chain Network")

    dcs = st.session_state.dcs
    demand = st.session_state.demand
    scenario = st.session_state.scenario
    results = st.session_state.results

    # --- manual controls (AI chat will call update_scenario() the same way) ---
    with st.expander("Adjust network manually", expanded=False):
        cols = st.columns(len(dcs))
        for col, (_, dc) in zip(cols, dcs.iterrows()):
            is_open = scenario["dc_status"][dc["dc_id"]] == "open"
            new_val = col.checkbox(dc["dc_id"], value=is_open)
            if new_val != is_open:
                update_scenario({"dc_status": {dc["dc_id"]: "open" if new_val else "closed"}})
                st.rerun()

    # --- map ---
    m = folium.Map(location=[51.0, 10.0], zoom_start=6, tiles="cartodbpositron")

    for _, dc in dcs.iterrows():
        is_open = scenario["dc_status"][dc["dc_id"]] == "open"
        folium.Marker(
            [dc["lat"], dc["lon"]],
            tooltip=f"{dc['dc_id']} ({'open' if is_open else 'closed'})",
            icon=folium.Icon(color="green" if is_open else "gray", icon="warehouse", prefix="fa"),
        ).add_to(m)

    for _, reg in demand.iterrows():
        folium.CircleMarker(
            [reg["lat"], reg["lon"]], radius=6, color="#3186cc", fill=True,
            tooltip=f"{reg['region_id']} — demand {reg['demand_units']} units",
        ).add_to(m)

    # draw flows if we have a solved scenario
    if results and results.get("feasible"):
        dc_coord = dcs.set_index("dc_id")[["lat", "lon"]]
        reg_coord = demand.set_index("region_id")[["lat", "lon"]]
        max_units = results["flows"]["units"].max()
        for _, f in results["flows"].iterrows():
            weight = 1 + 4 * (f["units"] / max_units)
            folium.PolyLine(
                [dc_coord.loc[f["dc_id"]].tolist(), reg_coord.loc[f["region_id"]].tolist()],
                weight=weight, opacity=0.6,
                color="#e67e22" if f["mode"] == "lsp" else "#2980b9",
                tooltip=f"{f['dc_id']} → {f['region_id']}: {f['units']} units ({f['mode']})",
            ).add_to(m)

    st_folium(m, width=None, height=520, returned_objects=[])

    st.caption("🔵 blue line = direct delivery · 🟠 orange line = via LSP · line thickness ≈ volume")
