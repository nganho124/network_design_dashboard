"""
Network optimization model using OR-Tools (GLOP linear solver).

Scope: given which warehouses are OPEN (a scenario input, not something the
solver decides — that's the user/AI chat's job), find the min-cost way to
route every store's demand (per product group) from open warehouses,
respecting each warehouse's capacity.

Cost = delivery (WH->Store) + inbound (Supplier->WH, weighted by the
baseline supply share) + handling (per pallet at the receiving WH) + fixed
cost of the open warehouses (a constant, since it doesn't depend on routing).

solve_network() is a PURE function: (scenario, reference data) -> results.
No Streamlit, no globals — same design as the original toy solver, just
rebuilt for the warehouse/store/pallet/multi-group schema.
"""

import pandas as pd
from ortools.linear_solver import pywraplp


def _weighted_inbound_cost(supply_baseline_share: pd.DataFrame, 
                           inbound_cost: pd.DataFrame) -> dict:
    """Precompute avg inbound cost per (wh_id, group_id), weighted by baseline supplier shares."""
    merged = supply_baseline_share.merge(
        inbound_cost[["supplier_id", "wh_id", "cost_per_pallet_eur"]], on=["supplier_id", "wh_id"])
    merged["weighted"] = merged["volume_share"] * merged["cost_per_pallet_eur"]
    avg = merged.groupby(["wh_id", "group_id"])["weighted"].sum()
    return avg.to_dict()  # {(wh_id, group_id): cost_per_pallet}


def solve_network(scenario: dict, 
                  warehouses: pd.DataFrame, 
                  stores: pd.DataFrame,
                  demand: pd.DataFrame, 
                  delivery_cost: pd.DataFrame, 
                  inbound_cost: pd.DataFrame,
                  supply_baseline_share: pd.DataFrame) -> dict:
    open_wh = [wh for wh, status in scenario["wh_status"].items() if status == "open"]
    if not open_wh:
        return {"feasible": False, "reason": "No warehouses are open — every store would be unserved."}

    total_capacity = warehouses[warehouses["wh_id"].isin(open_wh)]["capacity_pallets"].sum()
    total_demand = demand["demand_pallets"].sum()
    if total_capacity < total_demand:
        return {"feasible": False,
                "reason": f"Open warehouse capacity ({total_capacity:,.0f} plt) is below total "
                          f"demand ({total_demand:,.0f} plt) — open more warehouses."}

    avg_inbound = _weighted_inbound_cost(supply_baseline_share, inbound_cost)
    handling_cost = warehouses.set_index("wh_id")["handling_cost_eur_pallet"].to_dict()

    # plain dicts, not DataFrame .loc — .loc lookups inside a 50k+ iteration loop
    # were the dominant cost (~7s of a ~14s solve for the full 8-warehouse network)
    delivery_cost_dict = delivery_cost.set_index(["wh_id", "store_id"])["cost_per_pallet_eur"].to_dict()
    days_to_serve_dict = delivery_cost.set_index(["wh_id", "store_id"])["days_to_serve"].to_dict()

    solver = pywraplp.Solver.CreateSolver("GLOP")

    # --- decision variables: flow[wh, store, group] ---
    flow = {}
    demand_recs = demand.to_dict("records")
    for dr in demand_recs:
        store_id, group_id = dr["store_id"], dr["group_id"]
        for wh_id in open_wh:
            flow[(wh_id, store_id, group_id)] = solver.NumVar(
                0, solver.infinity(), f"f_{wh_id}_{store_id}_{group_id}")

    # --- demand satisfaction: every store-group fully served ---
    for dr in demand_recs:
        store_id, group_id, qty = dr["store_id"], dr["group_id"], dr["demand_pallets"]
        solver.Add(sum(flow[(wh_id, store_id, group_id)] for wh_id in open_wh) == qty)

    # --- capacity: each open warehouse bounded ---
    store_groups = [(dr["store_id"], dr["group_id"]) for dr in demand_recs]
    for wh_id in open_wh:
        cap = warehouses.loc[warehouses["wh_id"] == wh_id, "capacity_pallets"].iloc[0]
        solver.Add(sum(flow[(wh_id, s, g)] for s, g in store_groups) <= cap)

    # --- objective: delivery + inbound + handling, per pallet ---
    cost_terms = []
    for wh_id in open_wh:
        handling = handling_cost.get(wh_id, 0)
        for s, g in store_groups:
            delivery = delivery_cost_dict.get((wh_id, s), 0)
            inbound = avg_inbound.get((wh_id, g), 0)
            unit_cost = delivery + inbound + handling
            cost_terms.append(unit_cost * flow[(wh_id, s, g)])
    solver.Minimize(solver.Sum(cost_terms))

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return {"feasible": False, "reason": "Solver could not find an optimal solution."}

    # --- extract results ---
    rows = []
    for (wh_id, store_id, group_id), var in flow.items():
        val = var.solution_value()
        if val > 1e-6:
            rows.append({"wh_id": wh_id, "store_id": store_id, "group_id": group_id,
                        "pallets": val, "days_to_serve": days_to_serve_dict.get((wh_id, store_id), 0)})
    flows_detail = pd.DataFrame(rows)

    # aggregated to (wh_id, store_id) — this is what map_view.py / dashboard_view.py consume
    flows = flows_detail.groupby(["wh_id", "store_id"], as_index=False)["pallets"].sum()

    # vectorized cost totals (map/merge, not iterrows — iterrows over 7k+ rows was slow too)
    flows_detail["delivery_unit_cost"] = flows_detail.apply(
        lambda r: delivery_cost_dict.get((r["wh_id"], r["store_id"]), 0), axis=1)
    flows_detail["inbound_unit_cost"] = flows_detail.apply(
        lambda r: avg_inbound.get((r["wh_id"], r["group_id"]), 0), axis=1)
    flows_detail["handling_unit_cost"] = flows_detail["wh_id"].map(handling_cost)

    delivery_total = (flows_detail["pallets"] * flows_detail["delivery_unit_cost"]).sum()
    inbound_total = (flows_detail["pallets"] * flows_detail["inbound_unit_cost"]).sum()
    handling_total = (flows_detail["pallets"] * flows_detail["handling_unit_cost"]).sum()
    fixed_total = warehouses[warehouses["wh_id"].isin(open_wh)]["fixed_cost_eur_per_month"].sum()

    weighted_days = (flows_detail["pallets"] * flows_detail["days_to_serve"]).sum() / flows_detail["pallets"].sum()

    return {
        "feasible": True,
        "flows": flows,                    # aggregated wh_id/store_id/pallets — for map/dashboard
        "flows_detail": flows_detail,       # wh_id/store_id/group_id/pallets — for deeper inspection
        "delivery_cost_eur": round(delivery_total, 0),
        "inbound_cost_eur": round(inbound_total, 0),
        "handling_cost_eur": round(handling_total, 0),
        "fixed_cost_eur": round(fixed_total, 0),
        "total_cost_eur": round(delivery_total + inbound_total + handling_total + fixed_total, 0),
        "avg_days_to_serve": round(weighted_days, 2),
        "open_wh_count": len(open_wh),
    }