"""
Tab 1: Network map.

Reads from st.session_state.scenario / warehouses / stores / demand /
delivery_baseline_share (+ results, once solver.py is rewritten for this
schema) ONLY. Writes back to scenario via state.update_scenario() when the
user toggles a warehouse's status — never touches session_state directly.

Marker/line styling follows the reference dualNetworkMap() function:
- warehouses: folium.CustomIcon (image-based marker), colored by open/closed
- stores: small semi-transparent folium.CircleMarker with popup + tooltip
- flows: folium.PolyLine, width tiered by how many flow rows are being drawn
"""

from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from state import update_scenario, get_baseline_flows, get_effective_warehouses

ASSETS_DIR = Path(__file__).parent.parent / "data/assets"
ICON_OPEN = str(ASSETS_DIR / "warehouse_open.png")
ICON_CLOSED = str(ASSETS_DIR / "warehouse_closed.png")

# # Explicit tile URL + attribution instead of the "cartodbpositron" alias —
# # sidesteps folium/xyzservices version differences in alias resolution.
CARTO_KEY = "cb1_2uqf_1_27afec78ab53ef3242fb9a61"
CARTO_POSITRON_URL = f"https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png?key={CARTO_KEY}"
CARTO_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'

STORE_COLOR = "#2FA4D7"
LINE_COLOR = "#F4AE52"

@st.cache_resource(show_spinner=False)
def _build_map(_warehouses, _stores, _flows, open_wh_ids: tuple, flow_col: str, cache_key: str):
    """
    Builds the folium Map object. Cached on (open_wh_ids, cache_key) so
    toggling warehouses or re-solving doesn't rebuild all ~400 store markers
    on every Streamlit rerun — only when the actual inputs change.
    Leading-underscore params (_warehouses, _stores, _flows) are excluded
    from the cache key since DataFrames aren't hashable.
    """
    m = folium.Map(location=[51.0, 10.0], 
                   zoom_start=6,
                   tiles=CARTO_POSITRON_URL,
                   attr=CARTO_ATTR)

    # tiered line width by flow volume — same approach as the reference function
    # (fewer/wider lines are easier to read; many/thinner lines avoid clutter)
    line_width = 1.2 if len(_flows) <= 500 else 0.6

    # --- flows (drawn first, so markers sit on top) ---
    if not _flows.empty:
        wh_coord = _warehouses.set_index("wh_id")[["lat", "lon"]]
        store_coord = _stores.set_index("store_id")[["lat", "lon"]]
        for _, f in _flows.iterrows():
            if f["wh_id"] not in wh_coord.index or f["store_id"] not in store_coord.index:
                continue
            folium.PolyLine(
                locations=[wh_coord.loc[f["wh_id"]].tolist(), store_coord.loc[f["store_id"]].tolist()],
                color=LINE_COLOR, 
                weight=line_width, 
                opacity=0.6,
                tooltip=f"{f['wh_id']} → {f['store_id']}: {f[flow_col]:.1f} pallets",
            ).add_to(m)

    # --- warehouses: CustomIcon, colored by open/closed ---
    for _, wh in _warehouses.iterrows():
        is_open = wh["wh_id"] in open_wh_ids
        icon = folium.CustomIcon(ICON_OPEN if is_open else ICON_CLOSED, icon_size=(28, 28))
        is_greenfield = bool(wh.get("is_greenfield", False))
        if is_greenfield:
            # no pre-set capacity/fixed cost — sized to whatever the solver actually routes there
            size_note = "Capacity: sized to solved throughput (not yet built)"
        else:
            size_note = (f"Capacity: {wh['capacity_pallets']:,.0f} plt · "
                         f"Fixed cost: €{wh['fixed_cost_eur_per_month']:,.0f}/mo")
        name_note = f"{wh['wh_name']} 🏗️" if is_greenfield else wh["wh_name"]
        folium.Marker(
            [wh["lat"], wh["lon"]],
            tooltip=(f"{wh['wh_id']} — {name_note} ({'open' if is_open else 'closed'})<br>{size_note}"),
            icon=icon,
        ).add_to(m)

    # --- stores: small semi-transparent circle markers ---
    for _, s in _stores.iterrows():
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            popup=folium.Popup(f"Store: {s['store_id']}<br>City: {s['city']}", max_width=300),
            color=STORE_COLOR,
            radius=1,          # reference used 0.05 (px), which is sub-pixel and effectively
                                # invisible in-browser — bumped up so stores are actually visible
            opacity=0.8,
            tooltip=folium.map.Tooltip(f"Store ID: {s['store_id']}"),
            fill=True,
            fillOpacity=0.4,
        ).add_to(m)

    return m


def render_map_tab():
    # st.subheader("Supply Chain Network")

    warehouses = get_effective_warehouses()  # includes any greenfield sites added to this scenario
    stores = st.session_state.stores
    scenario = st.session_state.scenario
    results = st.session_state.results

    # --- manual controls (AI chat will call update_scenario() the same way) ---
    # with st.expander("Adjust network manually", expanded=False):
    #     cols = st.columns(4)
    #     for i, (_, wh) in enumerate(warehouses.iterrows()):
    #         is_open = scenario["wh_status"][wh["wh_id"]] == "open"
    #         label = f"{wh['wh_id']} — {wh['wh_name']}" + (" 🏗️" if wh.get("is_greenfield") else "")
    #         new_val = cols[i % 4].checkbox(label, value=is_open, key=f"wh_toggle_{wh['wh_id']}")
    #         if new_val != is_open:
    #             update_scenario({"wh_status": {wh["wh_id"]: "open" if new_val else "closed"}})
    #             st.rerun()

    # --- flows: prefer solved results once solver.py supports this schema; fall back to baseline ---
    if results and results.get("feasible"):
        flows = results["flows"]
        flow_col = "units" if "units" in flows.columns else "pallets"
        cache_key = f"solved:{results.get('total_cost_eur', 0)}"
    else:
        flows = get_baseline_flows()
        flow_col = "pallets"
        cache_key = "baseline"

    open_wh_ids = tuple(sorted(wh for wh, status in scenario["wh_status"].items() if status == "open"))

    m = _build_map(warehouses, stores, flows, open_wh_ids, flow_col, cache_key)
    st_folium(m, width=None, height=560, returned_objects=[])

    # if results and results.get("feasible"):
    #     st.caption("🟧 line = solved scenario flow · 🟢/⚫ warehouse = open/closed · "
    #                 "🔵 dot = store · line width ≈ flow density")
    # else:
    #     st.caption("🟧 line = baseline (fixed-share) flow, no scenario solved yet · "
    #                 "🟢/⚫ warehouse = open/closed · 🔵 dot = store · "
    #                 "closing a warehouse drops its flows but doesn't yet reallocate them "
    #                 "(pending solver update)")