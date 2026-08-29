"""
AI Supply Chain Network Advisor — main entry point.

Layout: 2 tabs (Map / Dashboard) + a sidebar reserved for the AI chat
(added at the hackathon — see chat_placeholder() below).
"""

import streamlit as st
from state import init_session_state, update_scenario
from solver import solve_network
from components.map_view import render_map_tab
from components.dashboard_view import render_dashboard_tab

st.set_page_config(page_title="AI Supply Chain Network Advisor", layout="wide")

init_session_state()


def solve_current_scenario():
    st.session_state.results = solve_network(
        st.session_state.scenario,
        st.session_state.dcs,
        st.session_state.demand,
        st.session_state.distance,
    )


def chat_placeholder():
    """
    Sidebar slot for the AI chat — build this out at the hackathon.

    The integration is intentionally small:
      1. Send user message + current scenario + get_scenario_schema_for_llm()
         to Claude with tool-use enabled.
      2. Claude returns a tool call with a partial scenario patch.
      3. Call update_scenario(patch) then solve_current_scenario().
      4. st.rerun()

    That's it — no other file needs to change.
    """
    st.sidebar.subheader("💬 Scenario Assistant")
    st.sidebar.caption("Coming at the build night — describe a scenario in plain language.")
    st.sidebar.text_input("e.g. 'Close Cologne and route everything via LSP'", disabled=True)


def main():
    st.title("🚚 AI Supply Chain Network Advisor")
    st.caption("Test different network setups before committing to a real restructuring decision.")

    chat_placeholder()

    # Delivery mode controls (manual, pre-AI) — lives here since it affects both tabs
    with st.sidebar:
        st.subheader("Delivery mode per region")
        for region_id in st.session_state.scenario["delivery_mode"]:
            current = st.session_state.scenario["delivery_mode"][region_id]
            choice = st.radio(region_id, ["direct", "lsp"],
                               index=0 if current == "direct" else 1,
                               key=f"mode_{region_id}", horizontal=True)
            if choice != current:
                update_scenario({"delivery_mode": {region_id: choice}})

        if st.button("🔄 Solve scenario", type="primary", use_container_width=True):
            solve_current_scenario()

    tab1, tab2 = st.tabs(["🗺️ Network Map", "📊 Dashboard"])
    with tab1:
        render_map_tab()
    with tab2:
        render_dashboard_tab()


if __name__ == "__main__":
    main()
