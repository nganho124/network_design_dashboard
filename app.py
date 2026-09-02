"""
AI Supply Chain Network Advisor — main entry point.

Layout: 2 tabs (Map / Dashboard) + a sidebar for scenario management
(solve / save / pick a saved scenario) and the AI chat (added at the
hackathon — see chat_placeholder() below).
"""

import pandas as pd
import streamlit as st

import db
from solver import solve_network
from state import init_session_state
from components.map_view import render_map_tab
from components.dashboard_view import render_dashboard_tab

st.set_page_config(page_title="AI Supply Chain Network Advisor", layout="wide")

init_session_state()
with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

LIVE_OPTION = "__live__"  # sentinel for "current, unsaved edits" in the scenario picker


def chat_placeholder():
    """
    Sidebar slot for the AI chat — build this out at the hackathon.

    The integration is intentionally small:
      1. Send user message + current scenario + get_scenario_schema_for_llm()
         to Claude with tool-use enabled.
      2. Claude returns a tool call with a partial scenario patch.
      3. Call update_scenario(patch) then solve_network() (see
         scenario_library_sidebar()'s "Solve" button for the call shape).
      4. st.rerun()

    That's it — no other file needs to change.
    """
    st.sidebar.subheader("💬 Scenario Assistant")
    st.sidebar.caption("Coming at the build night — describe a scenario in plain language.")
    st.sidebar.text_input("e.g. 'Close WH004 Cologne'", disabled=True)


def _solve_current_scenario():
    with st.spinner("Solving scenario..."):
        results = solve_network(
            st.session_state.scenario,
            st.session_state.warehouses,
            st.session_state.stores,
            st.session_state.demand,
            st.session_state.delivery_cost,
            st.session_state.inbound_cost,
            st.session_state.supply_share,
            st.session_state.inbound_cost_tiers,
            st.session_state.transfer_cost,
        )
    st.session_state.results = results
    st.session_state.active_scenario_id = None  # freshly solved, not yet saved


def scenario_library_sidebar():
    """
    Pick a saved scenario to view — Map/Dashboard switch to its solved result —
    or solve + save the scenario currently being edited via the map tab's
    warehouse toggles.

    st.session_state.active_scenario_id tracks which saved scenario (if any)
    is loaded; None means the warehouse toggles + results reflect a live,
    unsaved run (see update_scenario(), which clears it on any edit).
    """
    st.sidebar.subheader("📁 Scenario Library")

    saved = db.list_scenarios()
    # the LIVE_OPTION slot doubles as "Baseline" for the untouched default state (all
    # warehouses open, nothing solved yet) — the moment you toggle a warehouse or solve,
    # it's no longer the baseline, so relabel it "Live (unsaved edits)" instead
    is_untouched = st.session_state.results is None and all(
        s == "open" for s in st.session_state.scenario["wh_status"].values())
    labels = {LIVE_OPTION: "📍 Baseline (all warehouses open)" if is_untouched else "🟡 Live (unsaved edits)"}
    for _, row in saved.iterrows():
        flag = "✅" if row["feasible"] else "⚠️"
        cost = f"€{row['total_cost_eur']:,.0f}" if pd.notna(row["total_cost_eur"]) else "n/a"
        labels[row["scenario_id"]] = f"{flag} {row['name']} — {cost}"

    options = [LIVE_OPTION] + saved["scenario_id"].tolist()
    current = st.session_state.active_scenario_id or LIVE_OPTION
    if current not in options:
        current = LIVE_OPTION  # e.g. active scenario was deleted from the DB elsewhere

    selected = st.sidebar.selectbox(
        "Viewing", options, index=options.index(current), format_func=lambda opt: labels[opt],
        help="Choose a saved scenario to load its warehouse setup and solved result, "
             "or stay on 'Baseline' / 'Live' to keep editing from the current state.",
    )

    if selected != current:
        if selected == LIVE_OPTION:
            st.session_state.active_scenario_id = None
        else:
            record = db.load_scenario(selected)
            st.session_state.scenario = record["scenario_patch"]
            flows = record["flows"]
            st.session_state.results = {
                "feasible": bool(record["feasible"]),
                "flows": flows[["wh_id", "store_id", "pallets"]] if not flows.empty else flows,
                "total_cost_eur": record["total_cost_eur"],
                "avg_days_to_serve": record["avg_days_to_serve"],
            }
            st.session_state.active_scenario_id = selected
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("▶️ Solve current scenario", use_container_width=True):
        _solve_current_scenario()
        st.rerun()

    results = st.session_state.results
    if results and results.get("feasible"):
        cost = results.get("total_cost_eur")
        cost_str = f"€{cost:,.0f}/mo" if cost is not None else "n/a"
        if st.session_state.active_scenario_id:
            st.sidebar.success(f"✅ Feasible — {cost_str}. Already saved as this scenario "
                                f"— save again below to keep it as a new one too.")
        else:
            st.sidebar.success(f"✅ Feasible — {cost_str}. Name it below to save.")
        name = st.sidebar.text_input("Save as", placeholder="e.g. Close Cologne + consolidate imports")
        if st.sidebar.button("💾 Save scenario", use_container_width=True, disabled=not name.strip()):
            scenario_id = db.save_scenario(name.strip(), st.session_state.scenario, results, source="manual")
            st.session_state.active_scenario_id = scenario_id
            st.sidebar.success(f"Saved as '{name.strip()}'")
            st.rerun()
    elif results and not results.get("feasible"):
        st.sidebar.warning(f"⚠️ Infeasible — {results.get('reason', 'Scenario is infeasible.')} "
                            f"Nothing to save until it solves — adjust warehouses and re-solve.")
    else:
        st.sidebar.caption("Solve the current scenario to unlock saving.")


def main():
    st.title("🚚 AI Supply Chain Network Advisor")
    st.caption("Test different network setups before committing to a real restructuring decision.")

    chat_placeholder()
    scenario_library_sidebar()

    with st.sidebar:
        st.subheader("Warehouse status")
        wh_status = st.session_state.scenario["wh_status"]
        open_count = sum(1 for s in wh_status.values() if s == "open")
        st.metric("Open warehouses", f"{open_count} / {len(wh_status)}")
        st.caption("Toggle warehouses from the map tab's 'Adjust network manually' panel, "
                   "then Solve to see the reallocated network.")

    tab1, tab2 = st.tabs(["🗺️ Network Map", "📊 Dashboard"])
    with tab1:
        render_map_tab()
    with tab2:
        render_dashboard_tab()


if __name__ == "__main__":
    main()
