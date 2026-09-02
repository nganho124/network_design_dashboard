import streamlit as st
import pandas as pd

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
    product_groups = st.session_state.product_groups
    
    # 1. OUTBOUND / DELIVERY COST
    active_del_share = del_share[del_share["wh_id"].isin(open_wh_ids)]
    outbound = demand.merge(active_del_share, on=["store_id", "group_id"])
    outbound["allocated_pallets"] = outbound["demand_pallets"] * outbound["volume_share"]
    outbound = outbound.merge(del_cost, on=["wh_id", "store_id"])
    outbound["outbound_cost_eur"] = outbound["allocated_pallets"] * outbound["cost_per_pallet_eur"]
    
    total_outbound_vol = outbound["allocated_pallets"].sum()
    total_outbound_cost = outbound["outbound_cost_eur"].sum()

    # 2. WAREHOUSE COSTS
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
    inbound_flows = inbound.merge(suppliers[['supplier_id', 'type']], on='supplier_id')
    inbound_flows['supplier_group'] = inbound_flows['type'].str.capitalize() + " Suppliers"
    inbound_flows = inbound_flows.merge(warehouses[['wh_id', 'wh_name']], on='wh_id')
    inbound_flows = inbound_flows.merge(product_groups[['group_id', 'category']], on='group_id')
    
    outbound_flows = outbound.merge(warehouses[['wh_id', 'wh_name']], on='wh_id')
    outbound_flows = outbound_flows.merge(stores[['store_id', 'state']], on='store_id')
    outbound_flows = outbound_flows.merge(product_groups[['group_id', 'category']], on='group_id')

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