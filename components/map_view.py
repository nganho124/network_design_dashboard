"""
Tab 1: Network map.

Reads from st.session_state.scenario / warehouses / stores / demand /
delivery_baseline_share (+ results, once solver.py is rewritten for this
schema) ONLY. Writes back to scenario via state.update_scenario() when the
user toggles a warehouse's status — never touches session_state directly.
"""

import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from state import update_scenario, get_baseline_flows

# Explicit tile URL + attribution instead of the "cartodbpositron" alias.
# The alias resolves through folium's bundled xyzservices provider registry,
# which has changed behavior across versions — using the raw tile URL
# sidesteps that entirely and guarantees no API key is ever required.
FREE_TILE_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
FREE_TILE_ATTR = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
)


def render_map_tab():
    st.subheader("Supply Chain Network")

    warehouses = st.session_state.warehouses
    stores = st.session_state.stores
    scenario = st.session_state.scenario
    results = st.session_state.results

    # --- manual controls (AI chat will call update_scenario() the same way) ---
    with st.expander("Adjust network manually", expanded=False):
        cols = st.columns(4)
        for i, (_, wh) in enumerate(warehouses.iterrows()):
            is_open = scenario["wh_status"][wh["wh_id"]] == "open"
            label = f"{wh['wh_id']} — {wh['wh_name']}"
            new_val = cols[i % 4].checkbox(label, value=is_open, key=f"wh_toggle_{wh['wh_id']}")
            if new_val != is_open:
                update_scenario({"wh_status": {wh["wh_id"]: "open" if new_val else "closed"}})
                st.rerun()

    # --- base map ---
    m = folium.Map(location=[51.0, 10.0], zoom_start=6, tiles=FREE_TILE_URL, attr=FREE_TILE_ATTR)

    # warehouses: individual markers (only 8, no need to cluster)
    for _, wh in warehouses.iterrows():
        is_open = scenario["wh_status"][wh["wh_id"]] == "open"
        folium.Marker(
            [wh["lat"], wh["lon"]],
            tooltip=(f"{wh['wh_id']} — {wh['wh_name']} ({'open' if is_open else 'closed'})<br>"
                     f"Capacity: {wh['capacity_pallets']:,} plt · "
                     f"Fixed cost: €{wh['fixed_cost_eur_per_month']:,}/mo"),
            icon=folium.Icon(color="green" if is_open else "gray", icon="warehouse", prefix="fa"),
        ).add_to(m)

    # stores: clustered — 400 individual markers would be unreadable and slow to render
    store_cluster = MarkerCluster(name="Stores").add_to(m)
    for _, s in stores.iterrows():
        folium.CircleMarker(
            [s["lat"], s["lon"]], radius=4, color="#3186cc", fill=True, fill_opacity=0.8,
            tooltip=f"{s['store_id']} ({s['city']})",
        ).add_to(store_cluster)

    # --- flows: WH -> store ---
    # Prefer actual solver output once solver.py is rewritten for the
    # warehouse/store/pallet model; until then, fall back to the baseline
    # (fixed-share) flow derived straight from delivery_baseline_share x demand.
    if results and results.get("feasible"):
        flows = results["flows"]
        flow_col = "units" if "units" in flows.columns else "pallets"
    else:
        flows = get_baseline_flows()
        flow_col = "pallets"

    if not flows.empty:
        wh_coord = warehouses.set_index("wh_id")[["lat", "lon"]]
        store_coord = stores.set_index("store_id")[["lat", "lon"]]
        max_flow = flows[flow_col].max()

        for _, f in flows.iterrows():
            if f["wh_id"] not in wh_coord.index or f["store_id"] not in store_coord.index:
                continue
            weight = 0.5 + 2.5 * (f[flow_col] / max_flow)
            folium.PolyLine(
                [wh_coord.loc[f["wh_id"]].tolist(), store_coord.loc[f["store_id"]].tolist()],
                weight=weight, opacity=0.35, color="#2980b9",
                tooltip=f"{f['wh_id']} → {f['store_id']}: {f[flow_col]:.1f} pallets",
            ).add_to(m)

    st_folium(m, width=None, height=560, returned_objects=[])

    if results and results.get("feasible"):
        st.caption("🔵 line = solved scenario flow · thickness ≈ pallet volume")
    else:
        st.caption("🔵 line = baseline (fixed-share) flow, no scenario solved yet · "
                    "thickness ≈ pallet volume · closing a warehouse drops its flows "
                    "but doesn't yet reallocate them (pending solver update)")