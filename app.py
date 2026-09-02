"""
AI Supply Chain Network Advisor — main entry point.

Layout: 2 tabs (Map / Dashboard) + a sidebar reserved for the AI chat
(added at the hackathon — see chat_placeholder() below).
"""

import streamlit as st
from state import init_session_state
from components.map_view import render_map_tab
from components.dashboard_view import render_dashboard_tab

st.set_page_config(page_title="AI Supply Chain Network Advisor", layout="wide")

init_session_state()
with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def chat_placeholder():
    """
    Sidebar slot for the AI chat — build this out at the hackathon.

    The integration is intentionally small:
      1. Send user message + current scenario + get_scenario_schema_for_llm()
         to Claude with tool-use enabled.
      2. Claude returns a tool call with a partial scenario patch.
      3. Call update_scenario(patch) then solve_current_scenario() (once solver.py
         is rewritten for the warehouse/store/pallet model).
      4. st.rerun()

    That's it — no other file needs to change.
    """
    st.sidebar.subheader("💬 Scenario Assistant")
    st.sidebar.caption("Coming at the build night — describe a scenario in plain language.")
    st.sidebar.text_input("e.g. 'Close WH004 Cologne'", disabled=True)


def main():
    st.title("🚚 AI Supply Chain Network Advisor")
    st.caption("Test different network setups before committing to a real restructuring decision.")

    chat_placeholder()

    with st.sidebar:
        st.subheader("Warehouse status")
        wh_status = st.session_state.scenario["wh_status"]
        open_count = sum(1 for s in wh_status.values() if s == "open")
        st.metric("Open warehouses", f"{open_count} / {len(wh_status)}")
        st.caption("Toggle warehouses from the map tab's 'Adjust network manually' panel.")
        st.info("⚠️ Scenario solving isn't wired up yet — the map currently shows the "
                "**baseline** (fixed-share) network. Closing a warehouse hides its flows "
                "but doesn't reallocate demand elsewhere until solver.py is rewritten "
                "for this warehouse/store/pallet model.", icon="⚠️")

    tab1, tab2 = st.tabs(["🗺️ Network Map", "📊 Dashboard"])
    with tab1:
        render_map_tab()
    with tab2:
        render_dashboard_tab()


if __name__ == "__main__":
    main()