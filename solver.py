"""
Network optimization model using OR-Tools (GLOP linear solver).

This solves a transportation problem: given which DCs are open and the
delivery mode chosen per region, find the min-cost way to serve all
region demand from open DCs within their capacity.

solve_network() is intentionally a PURE function: (scenario, reference data) -> results.
No Streamlit, no globals. This is what makes it a clean target for:
  - manual UI controls (app.py calls it after any widget change)
  - the AI chat tool-call on hackathon night (same function, same signature)
"""

import pandas as pd
from ortools.linear_solver import pywraplp


def solve_network(scenario: dict, dcs: pd.DataFrame, demand: pd.DataFrame,
                   distance: pd.DataFrame) -> dict:
    dc_status = scenario["dc_status"]
    delivery_mode = scenario["delivery_mode"]

    open_dcs = [d for d, status in dc_status.items() if status == "open"]
    if not open_dcs:
        return {"feasible": False, "reason": "No DCs are open — every region would be unserved."}

    solver = pywraplp.Solver.CreateSolver("GLOP")

    # Decision vars: flow[dc, region] = units shipped, only for open DCs
    flow = {}
    for dc_id in open_dcs:
        for _, reg in demand.iterrows():
            flow[(dc_id, reg["region_id"])] = solver.NumVar(0, solver.infinity(), f"flow_{dc_id}_{reg['region_id']}")

    # Demand satisfaction: each region's demand must be fully met
    for _, reg in demand.iterrows():
        solver.Add(
            sum(flow[(dc_id, reg["region_id"])] for dc_id in open_dcs) == reg["demand_units"]
        )

    # Capacity constraint: each open DC can't exceed its capacity
    for dc_id in open_dcs:
        cap = dcs.loc[dcs["dc_id"] == dc_id, "capacity_units"].iloc[0]
        solver.Add(
            sum(flow[(dc_id, reg["region_id"])] for reg in demand.to_dict("records")) <= cap
        )

    # Objective: minimize total transport cost (mode-dependent, per region)
    dist_lookup = distance.set_index(["dc_id", "region_id"])
    cost_terms = []
    for dc_id in open_dcs:
        for _, reg in demand.iterrows():
            mode = delivery_mode.get(reg["region_id"], "direct")
            cost_col = "cost_per_unit_direct" if mode == "direct" else "cost_per_unit_lsp"
            unit_cost = dist_lookup.loc[(dc_id, reg["region_id"]), cost_col]
            cost_terms.append(unit_cost * flow[(dc_id, reg["region_id"])])
    solver.Minimize(solver.Sum(cost_terms))

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return {"feasible": False, "reason": "No feasible solution — check DC capacity vs total demand."}

    # Extract flows
    flow_rows = []
    for (dc_id, region_id), var in flow.items():
        units = var.solution_value()
        if units > 1e-3:
            mode = delivery_mode.get(region_id, "direct")
            days_col = "days_to_serve_direct" if mode == "direct" else "days_to_serve_lsp"
            days = dist_lookup.loc[(dc_id, region_id), days_col]
            flow_rows.append({
                "dc_id": dc_id, "region_id": region_id, "units": round(units, 1),
                "mode": mode, "days_to_serve": days,
            })
    flows_df = pd.DataFrame(flow_rows)

    total_cost = solver.Objective().Value()
    fixed_cost = dcs[dcs["dc_id"].isin(open_dcs)]["fixed_cost_eur"].sum()
    weighted_days = (flows_df["units"] * flows_df["days_to_serve"]).sum() / flows_df["units"].sum()

    return {
        "feasible": True,
        "total_variable_cost_eur": round(total_cost, 0),
        "total_fixed_cost_eur": round(fixed_cost, 0),
        "total_cost_eur": round(total_cost + fixed_cost, 0),
        "avg_days_to_serve": round(weighted_days, 2),
        "open_dc_count": len(open_dcs),
        "flows": flows_df,
    }
