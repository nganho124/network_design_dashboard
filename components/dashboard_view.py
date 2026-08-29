"""
Tab 2: KPI dashboard.

Reads ONLY from st.session_state.results (produced by solver.solve_network).
Never triggers a solve itself — app.py owns when solving happens.
"""

import streamlit as st
import plotly.express as px
import pandas as pd


def render_dashboard_tab():
    st.subheader("Scenario Impact")

    results = st.session_state.results
    if results is None:
        st.info("No scenario solved yet — adjust the network on the Map tab.")
        return
    if not results.get("feasible"):
        st.error(results.get("reason", "Scenario is infeasible."))
        return

    # --- KPI row ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total cost / period", f"€{results['total_cost_eur']:,.0f}")
    c2.metric("Variable (transport) cost", f"€{results['total_variable_cost_eur']:,.0f}")
    c3.metric("Fixed (DC) cost", f"€{results['total_fixed_cost_eur']:,.0f}")
    c4.metric("Avg. days to serve", f"{results['avg_days_to_serve']:.1f} d")

    flows = results["flows"]

    col1, col2 = st.columns(2)

    with col1:
        cost_by_dc = flows.groupby("dc_id")["units"].sum().reset_index()
        fig1 = px.bar(cost_by_dc, x="dc_id", y="units", title="Volume served per DC",
                      labels={"units": "Units", "dc_id": "Distribution Center"})
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        mode_split = flows.groupby("mode")["units"].sum().reset_index()
        fig2 = px.pie(mode_split, names="mode", values="units", title="Direct vs. LSP volume split")
        st.plotly_chart(fig2, use_container_width=True)

    fig3 = px.bar(
        flows, x="region_id", y="units", color="dc_id", title="Which DC serves each region",
        labels={"units": "Units", "region_id": "Region"},
    )
    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("Raw flow table"):
        st.dataframe(flows, use_container_width=True)
