"""
Tab 2: KPI dashboard.

Dynamically calculates network costs, metrics, and network flows based on the 
current scenario's open/closed warehouses. Compares against the baseline.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

def calculate_dashboard_metrics(open_wh_ids):
    """
    Applies the business logic to calculate costs and flows for a specific set of open warehouses.
    """
    demand = st.session_state.demand
    del_share = st.session_state.delivery_baseline_share
    del_cost = st.session_state.delivery_cost
    sup_share = st.session_state.supply_baseline_share
    in_cost = st.session_state.inbound_cost
    
    warehouses = st.session_state.warehouses
    stores = st.session_state.stores
    suppliers = st.session_state.suppliers
    
    # 1. OUTBOUND / DELIVERY COST
    active_del_share = del_share[del_share["wh_id"].isin(open_wh_ids)]
    outbound = demand.merge(active_del_share, on=["store_id", "group_id"])
    outbound["allocated_pallets"] = outbound["demand_pallets"] * outbound["volume_share"]
    outbound = outbound.merge(del_cost, on=["wh_id", "store_id"])
    outbound["outbound_cost_eur"] = outbound["allocated_pallets"] * outbound["cost_per_pallet_eur"]
    
    total_outbound_vol = outbound["allocated_pallets"].sum()
    total_outbound_cost = outbound["outbound_cost_eur"].sum()

    # 2. WAREHOUSE COSTS (Handling & Storage/Fixed)
    wh_throughput = outbound.groupby("wh_id")["allocated_pallets"].sum().reset_index()
    active_wh = warehouses[warehouses["wh_id"].isin(open_wh_ids)].copy()
    wh_calc = active_wh.merge(wh_throughput, on="wh_id", how="left").fillna(0)
    
    wh_calc["handling_cost_eur"] = wh_calc["handling_cost_eur_pallet"] * 2 * wh_calc["allocated_pallets"]
    wh_calc["fixed_cost_eur"] = wh_calc["fixed_cost_eur_per_month"]
    
    total_handling_cost = wh_calc["handling_cost_eur"].sum()
    total_fixed_cost = wh_calc["fixed_cost_eur"].sum()

    # 3. INBOUND COST
    wh_group_demand = outbound.groupby(["wh_id", "group_id"])["allocated_pallets"].sum().reset_index()
    inbound = wh_group_demand.merge(sup_share, on=["wh_id", "group_id"])
    inbound["inbound_pallets"] = inbound["allocated_pallets"] * inbound["volume_share"]
    inbound = inbound.merge(in_cost, on=["supplier_id", "wh_id"])
    inbound["inbound_cost_eur"] = inbound["inbound_pallets"] * inbound["cost_per_pallet_eur"]
    
    total_inbound_cost = inbound["inbound_cost_eur"].sum()

    # 4. PREPARE SANKEY FLOW DATA
    # Attach names for readability in the Sankey Chart
    inbound_flows = inbound.merge(suppliers[['supplier_id', 'name']], on='supplier_id')
    inbound_flows = inbound_flows.merge(warehouses[['wh_id', 'wh_name']], on='wh_id')
    
    outbound_flows = outbound.merge(warehouses[['wh_id', 'wh_name']], on='wh_id')
    outbound_flows = outbound_flows.merge(stores[['store_id', 'city']], on='store_id')

    # Compile results
    total_cost = total_inbound_cost + total_handling_cost + total_fixed_cost + total_outbound_cost
    unit_cost = total_cost / total_outbound_vol if total_outbound_vol > 0 else 0

    return {
        "volume_pallets": total_outbound_vol,
        "inbound_cost": total_inbound_cost,
        "handling_cost": total_handling_cost,
        "fixed_cost": total_fixed_cost,
        "outbound_cost": total_outbound_cost,
        "total_cost": total_cost,
        "unit_cost": unit_cost,
        "wh_details": wh_calc,
        "inbound_flows": inbound_flows,
        "outbound_flows": outbound_flows
    }


def build_sankey_chart(metrics_data, title):
    """
    Generates a Plotly Sankey diagram charting Supplier -> Warehouse -> Store City.
    """
    in_agg = metrics_data['inbound_flows'].groupby(['name', 'wh_name'])['inbound_pallets'].sum().reset_index()
    out_agg = metrics_data['outbound_flows'].groupby(['wh_name', 'city'])['allocated_pallets'].sum().reset_index()

    # Create a unique list of all nodes
    all_nodes = list(pd.concat([
        in_agg['name'], in_agg['wh_name'],
        out_agg['wh_name'], out_agg['city']
    ]).unique())

    node_dict = {node: i for i, node in enumerate(all_nodes)}
    
    sources, targets, values = [], [], []

    # Map Supplier -> Warehouse
    for _, row in in_agg.iterrows():
        if row['inbound_pallets'] > 0:
            sources.append(node_dict[row['name']])
            targets.append(node_dict[row['wh_name']])
            values.append(row['inbound_pallets'])

    # Map Warehouse -> Store City (Aggregated to prevent 400+ nodes)
    for _, row in out_agg.iterrows():
        if row['allocated_pallets'] > 0:
            sources.append(node_dict[row['wh_name']])
            targets.append(node_dict[row['city']])
            values.append(row['allocated_pallets'])

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=15, thickness=20,
            line=dict(color="black", width=0.5),
            label=all_nodes,
            color="#385D7F"
        ),
        link=dict(
            source=sources, target=targets, value=values,
            color="rgba(192, 192, 192, 0.4)"
        )
    )])
    fig.update_layout(title_text=title, font_size=10, height=500, margin=dict(t=40, b=20, l=0, r=0))
    return fig


def render_dashboard_tab():
    st.subheader("Scenario Impact Dashboard")

    required_tables = ["demand", "delivery_baseline_share", "delivery_cost", 
                       "supply_baseline_share", "inbound_cost", "warehouses", "stores", "suppliers"]
    if any(tbl not in st.session_state for tbl in required_tables):
        st.warning("Data tables are missing. Please ensure all 9 tables are loaded in state.py.")
        return

    # Determine state: Baseline vs Scenario
    baseline_wh_ids = st.session_state.warehouses["wh_id"].tolist()
    scenario_wh_ids = [wh_id for wh_id, status in st.session_state.scenario["wh_status"].items() if status == "open"]
    
    is_scenario = set(baseline_wh_ids) != set(scenario_wh_ids)

    with st.spinner("Calculating network metrics..."):
        base_metrics = calculate_dashboard_metrics(baseline_wh_ids)
        if is_scenario:
            scen_metrics = calculate_dashboard_metrics(scenario_wh_ids)
            display_metrics = scen_metrics
        else:
            display_metrics = base_metrics

    # --- KPI Row ---
    st.markdown(f"### Top-Level KPIs {'(Scenario Comparison)' if is_scenario else '(Baseline)'}")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    
    def render_metric(col, label, key, prefix="€", suffix=""):
        val = display_metrics[key]
        if is_scenario:
            delta = val - base_metrics[key]
            delta_color = "normal" if key == "volume_pallets" else "inverse"
            col.metric(label, f"{prefix}{val:,.0f}{suffix}", delta=float(delta), delta_color=delta_color)
        else:
            col.metric(label, f"{prefix}{val:,.0f}{suffix}")

    render_metric(c1, "Total Volume", "volume_pallets", prefix="", suffix=" PLT")
    render_metric(c2, "Inbound Cost", "inbound_cost")
    
    wh_op_val = display_metrics["handling_cost"] + display_metrics["fixed_cost"]
    if is_scenario:
        wh_op_base = base_metrics["handling_cost"] + base_metrics["fixed_cost"]
        c3.metric("WH Operations Cost", f"€{wh_op_val:,.0f}", delta=float(wh_op_val - wh_op_base), delta_color="inverse")
    else:
        c3.metric("WH Operations Cost", f"€{wh_op_val:,.0f}")

    render_metric(c4, "Outbound Cost", "outbound_cost")
    
    uc_val = display_metrics["unit_cost"]
    if is_scenario:
        uc_delta = uc_val - base_metrics["unit_cost"]
        c5.metric("Total Unit Cost", f"€{uc_val:.2f} / PLT", delta=float(uc_delta), delta_color="inverse")
    else:
        c5.metric("Total Unit Cost", f"€{uc_val:.2f} / PLT")

    st.markdown("---")

    # --- Sankey Flow Chart ---
    st.header("Network Flow Section")
    with st.expander("Sankey Chart: Supplier → Warehouse → City", expanded=True):
        if is_scenario:
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.plotly_chart(build_sankey_chart(base_metrics, "Baseline Flow"), use_container_width=True)
            with s_col2:
                st.plotly_chart(build_sankey_chart(scen_metrics, "Scenario Flow"), use_container_width=True)
        else:
            st.plotly_chart(build_sankey_chart(base_metrics, "Baseline Flow"), use_container_width=True)

    st.markdown("---")

    # --- Cost Breakdown Charts ---
    st.subheader("Breakdown by Cost Components", divider='blue')
    waterfall_col1, waterfall_col2 = st.columns(2)
    
    components = ['Inbound', 'Handling', 'Fixed (Storage)', 'Outbound']
    
    def build_comparison_chart(base_vals, scen_vals, prefix="€", suffix=""):
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Baseline', x=components, y=base_vals,
            marker_color='#385D7F', text=[f"{prefix}{v:,.0f}{suffix}" for v in base_vals], textposition='auto'
        ))
        if is_scenario:
            fig.add_trace(go.Bar(
                name='Scenario', x=components, y=scen_vals,
                marker_color='#CB333B', text=[f"{prefix}{v:,.0f}{suffix}" for v in scen_vals], textposition='auto'
            ))
        fig.update_layout(barmode='group', height=400, margin=dict(t=20, b=20, l=0, r=0), 
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        return fig

    base_abs = [base_metrics['inbound_cost'], base_metrics['handling_cost'], base_metrics['fixed_cost'], base_metrics['outbound_cost']]
    scen_abs = [display_metrics['inbound_cost'], display_metrics['handling_cost'], display_metrics['fixed_cost'], display_metrics['outbound_cost']]
    
    with waterfall_col1:
        st.markdown("**Absolute Costs (EUR)**")
        st.plotly_chart(build_comparison_chart(base_abs, scen_abs), use_container_width=True)

    base_unit = [c / base_metrics['volume_pallets'] if base_metrics['volume_pallets'] > 0 else 0 for c in base_abs]
    scen_unit = [c / display_metrics['volume_pallets'] if display_metrics['volume_pallets'] > 0 else 0 for c in scen_abs]
    
    with waterfall_col2:
        st.markdown("**Cost per Pallet (EUR/PLT)**")
        st.plotly_chart(build_comparison_chart(base_unit, scen_unit), use_container_width=True)

    st.markdown("---")

    # --- Warehouse Utilization ---
    st.header('Warehouse Section')
    with st.expander("Capacity Utilization Comparison", expanded=True):
        wh_base = base_metrics['wh_details'][['wh_name', 'capacity_pallets', 'allocated_pallets']].copy()
        wh_base.rename(columns={'allocated_pallets': 'base_used'}, inplace=True)
        
        if is_scenario:
            wh_scen = scen_metrics['wh_details'][['wh_name', 'allocated_pallets']].copy()
            wh_scen.rename(columns={'allocated_pallets': 'scen_used'}, inplace=True)
            wh_chart = wh_base.merge(wh_scen, on='wh_name', how='left').fillna(0)
        else:
            wh_chart = wh_base.copy()
            wh_chart['scen_used'] = wh_chart['base_used']

        wh_chart = wh_chart.sort_values('capacity_pallets', ascending=True)

        fig_util = go.Figure()
        fig_util.add_trace(go.Bar(
            y=wh_chart['wh_name'], x=wh_chart['base_used'],
            name='Baseline Used', orientation='h', marker_color='#385D7F'
        ))
        
        if is_scenario:
            fig_util.add_trace(go.Bar(
                y=wh_chart['wh_name'], x=wh_chart['scen_used'],
                name='Scenario Used', orientation='h', marker_color='#CB333B'
            ))
            
        fig_util.add_trace(go.Scatter(
            y=wh_chart['wh_name'], x=wh_chart['capacity_pallets'],
            name='Max Capacity', mode='markers',
            marker=dict(symbol='line-ns', size=20, color='black', line=dict(width=3))
        ))

        fig_util.update_layout(
            barmode='group',
            height=max(400, len(wh_chart) * 45),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_util, use_container_width=True)