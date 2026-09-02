"""
Tab 2: KPI dashboard.

Orchestrates the layout of the KPI dashboard, importing calculation logic 
and visualizations from the util/ modules.
"""

import streamlit as st

# Import refactored utility modules
import util.helper_calculation as help_cal
import util.helper_kpis_card as kpis_card
import util.helper_sankey as help_sankey
import util.helper_visualization as help_viz
import util.helper_waterfall_chart as help_wtf

def render_dashboard_tab():
    st.subheader("Scenario Impact Dashboard")

    required_tables = ["demand", "delivery_baseline_share", "delivery_cost", 
                       "supply_baseline_share", "inbound_cost", "warehouses", 
                       "stores", "suppliers", "product_groups"]
                       
    if any(tbl not in st.session_state for tbl in required_tables):
        st.warning("Data tables are missing. Please ensure all 9 tables are loaded in state.py.")
        return

    baseline_wh_ids = st.session_state.warehouses["wh_id"].tolist()
    scenario_wh_ids = [wh_id for wh_id, status in st.session_state.scenario["wh_status"].items() if status == "open"]
    
    is_scenario = set(baseline_wh_ids) != set(scenario_wh_ids)

    with st.spinner("Calculating network metrics..."):
        base_metrics = help_cal.calculate_dashboard_metrics(baseline_wh_ids)
        if is_scenario:
            scen_metrics = help_cal.calculate_dashboard_metrics(scenario_wh_ids)
            display_metrics = scen_metrics
        else:
            display_metrics = base_metrics

    # ==========================================
    # 1. KPI SECTION
    # ==========================================
    st.markdown(f"### Top-Level KPIs {'(Scenario Comparison)' if is_scenario else '(Baseline)'}")
    c1, c2, c3, c4, c5 = st.columns(5)
    
    main_name = "Scenario" if is_scenario else "Baseline"
    compare_name = "Baseline"
    card_color = "var(--primary-color)"
    
    kpis_card.create_kpi_card(
        main_name, "Total Volume", compare_name, 
        display_metrics["volume_pallets"], base_metrics["volume_pallets"], 
        c1, "PLT", card_color
    )
    
    kpis_card.create_kpi_card_wbackground(
        main_name, "Inbound Cost", compare_name, 
        display_metrics["inbound_cost"], base_metrics["inbound_cost"], 
        c2, "EUR", card_color
    )
    
    wh_op_val = display_metrics["handling_cost"] + display_metrics["fixed_cost"]
    wh_op_base = base_metrics["handling_cost"] + base_metrics["fixed_cost"]
    kpis_card.create_kpi_card_wbackground(
        main_name, "WH Operations Cost", compare_name, 
        wh_op_val, wh_op_base, 
        c3, "EUR", card_color
    )
    
    kpis_card.create_kpi_card_wbackground(
        main_name, "Outbound Cost", compare_name, 
        display_metrics["outbound_cost"], base_metrics["outbound_cost"], 
        c4, "EUR", card_color
    )
    
    kpis_card.create_kpi_card_wbackground(
        main_name, "Total Unit Cost", compare_name, 
        display_metrics["unit_cost"], base_metrics["unit_cost"], 
        c5, "EUR / PLT", card_color
    )

    st.markdown("---")

    # ==========================================
    # 2. FLOW SECTION
    # ==========================================
    st.header("Network Flow Section")
    with st.expander("Sankey Chart: Supplier → Warehouse → State", expanded=True):
        if is_scenario:
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.plotly_chart(help_sankey.build_sankey_chart(base_metrics, "Baseline Flow"), use_container_width=True)
            with s_col2:
                st.plotly_chart(help_sankey.build_sankey_chart(scen_metrics, "Scenario Flow"), use_container_width=True)
        else:
            st.plotly_chart(help_sankey.build_sankey_chart(base_metrics, "Baseline Flow"), use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 3. COST BREAKDOWN SECTION
    # ==========================================
    st.subheader("Breakdown by Cost Components", divider='blue')
    waterfall_col1, waterfall_col2 = st.columns(2)
    
    components = ['Inbound', 'Handling', 'Fixed (Storage)', 'Outbound']
    
    base_abs = [base_metrics['inbound_cost'], base_metrics['handling_cost'], base_metrics['fixed_cost'], base_metrics['outbound_cost']]
    scen_abs = [display_metrics['inbound_cost'], display_metrics['handling_cost'], display_metrics['fixed_cost'], display_metrics['outbound_cost']]
    
    with waterfall_col1:
        st.markdown("**Absolute Costs (EUR)**")
        help_wtf.render_highcharts_waterfall(
            components, base_abs, scen_abs, is_scenario, 
            value_title="Absolute EUR", format_millions=True 
        )

    base_unit = [c / base_metrics['volume_pallets'] if base_metrics['volume_pallets'] > 0 else 0 for c in base_abs]
    scen_unit = [c / display_metrics['volume_pallets'] if display_metrics['volume_pallets'] > 0 else 0 for c in scen_abs]
    
    with waterfall_col2:
        st.markdown("**Cost per Pallet (EUR/PLT)**")
        help_wtf.render_highcharts_waterfall(
            components, base_unit, scen_unit, is_scenario, 
            value_title="EUR / PLT", format_millions=False 
        )

    st.markdown("---")

    # ==========================================
    # 4. WAREHOUSE UTILIZATION SECTION
    # ==========================================
    st.header('Warehouse Section')
    with st.expander("Capacity Utilization Comparison", expanded=True):
        
        wh_base = base_metrics['wh_details'][['wh_name', 'capacity_pallets', 'allocated_pallets']].copy()
        wh_base.rename(columns={'allocated_pallets': 'base_used'}, inplace=True)
        
        wh_scen = None
        if is_scenario:
            wh_scen = scen_metrics['wh_details'][['wh_name', 'allocated_pallets']].copy()
            wh_scen.rename(columns={'allocated_pallets': 'scen_used'}, inplace=True)

        util_chart = help_viz.build_capacity_utilization_chart(wh_base, wh_scen, is_scenario)
        st.plotly_chart(util_chart, use_container_width=True)