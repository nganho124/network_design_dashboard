"""
Network optimization model using OR-Tools (CBC MIP solver).

Scope: given which warehouses are OPEN (a scenario input, not something the
solver decides — that's the user/AI chat's job), find the min-cost way to:

  - SOURCE each open warehouse's inbound volume from ELIGIBLE suppliers.
    supply_share (Supplier x Group, network-wide, no wh_id) caps how much of
    a group's total demand any one supplier can realistically cover — the
    solver picks the actual supplier -> WH assignment, it isn't fixed to a
    baseline split.
  - Optionally CONSOLIDATE international (import) volume onto fewer
    (supplier, WH) shipments to earn a cheaper stepped import rate
    (inbound_cost_tiers — bigger shipments are cheaper per pallet), then
    redistribute via an internal WH -> WH TRANSFER (transfer_cost) to the
    warehouse that actually needs the volume, trading the import discount
    against transfer + extra handling cost.
  - ROUTE every store's demand (per product group) from open warehouses,
    respecting each warehouse's throughput capacity.

Import cost is a step function of shipment size (an "all-units quantity
discount"), which needs binary tier-selection variables — so this is a MIP,
solved with CBC, not the plain LP (GLOP) used previously.

solve_network() is a PURE function: (scenario, reference data) -> results.
No Streamlit, no globals.
"""

import pandas as pd
from ortools.linear_solver import pywraplp


def solve_network(scenario: dict,
                   warehouses: pd.DataFrame,
                   stores: pd.DataFrame,
                   demand: pd.DataFrame,
                   delivery_cost: pd.DataFrame,
                   inbound_cost: pd.DataFrame,
                   supply_share: pd.DataFrame,
                   inbound_cost_tiers: pd.DataFrame,
                   transfer_cost: pd.DataFrame) -> dict:
    open_wh = [wh for wh, status in scenario["wh_status"].items() if status == "open"]
    if not open_wh:
        return {"feasible": False, "reason": "No warehouses are open — every store would be unserved."}

    total_capacity = warehouses[warehouses["wh_id"].isin(open_wh)]["capacity_pallets"].sum()
    total_demand = float(demand["demand_pallets"].sum())
    if total_capacity < total_demand:
        return {"feasible": False,
                "reason": f"Open warehouse capacity ({total_capacity:,.0f} plt) is below total "
                          f"demand ({total_demand:,.0f} plt) — open more warehouses."}

    solver = pywraplp.Solver.CreateSolver("CBC")
    inf = solver.infinity()

    handling_cost = warehouses.set_index("wh_id")["handling_cost_eur_pallet"].to_dict()
    delivery_cost_dict = delivery_cost.set_index(["wh_id", "store_id"])["cost_per_pallet_eur"].to_dict()
    days_to_serve_dict = delivery_cost.set_index(["wh_id", "store_id"])["days_to_serve"].to_dict()
    inbound_cost_dict = inbound_cost.set_index(["supplier_id", "wh_id"])["cost_per_pallet_eur"].to_dict()
    transfer_cost_dict = transfer_cost.set_index(["wh_id_from", "wh_id_to"])["cost_per_pallet_eur"].to_dict()

    demand_recs = demand.to_dict("records")
    store_groups = [(dr["store_id"], dr["group_id"]) for dr in demand_recs]
    groups = sorted(demand["group_id"].unique())

    # --- eligible (supplier, group) pairs and each supplier's network-wide cap ---
    # SUPPLIER_CAP_SLACK: shares are rounded to 4dp, so per-group caps sum to ~1.0 but not
    # exactly — without slack, that rounding gap alone can make the demand-satisfaction
    # constraint infeasible. A few % of headroom also reflects that a supplier's real
    # capacity isn't a hard cutoff at its nominal baseline share.
    SUPPLIER_CAP_SLACK = 1.05
    total_group_demand = demand.groupby("group_id")["demand_pallets"].sum().to_dict()
    eligible = supply_share[supply_share["volume_share"] > 0]
    supplier_cap = {
        (r["supplier_id"], r["group_id"]):
            r["volume_share"] * total_group_demand.get(r["group_id"], 0) * SUPPLIER_CAP_SLACK
        for _, r in eligible.iterrows()
    }
    eligible_suppliers_by_group = {}
    for sid, gid in supplier_cap:
        eligible_suppliers_by_group.setdefault(gid, []).append(sid)

    # --- (supplier, wh) pairs that use stepped import pricing instead of a flat rate ---
    tiers_by_pair = {}
    for _, row in inbound_cost_tiers.iterrows():
        tiers_by_pair.setdefault((row["supplier_id"], row["wh_id"]), []).append(row)

    # =========================================================================
    # Decision variables
    # =========================================================================

    # distribution flow: wh -> store, per group
    dist_flow = {}
    for dr in demand_recs:
        store_id, group_id = dr["store_id"], dr["group_id"]
        for wh_id in open_wh:
            dist_flow[(wh_id, store_id, group_id)] = solver.NumVar(0, inf, f"d_{wh_id}_{store_id}_{group_id}")

    # sourcing flow: supplier -> wh, per group (only eligible supplier/group pairs)
    inbound_flow = {}
    for gid, sids in eligible_suppliers_by_group.items():
        for sid in sids:
            for wh_id in open_wh:
                inbound_flow[(sid, wh_id, gid)] = solver.NumVar(0, inf, f"s_{sid}_{wh_id}_{gid}")

    # transfer flow: wh -> wh, per group (open warehouses only, no self-loop)
    transfer_flow = {}
    for gid in groups:
        for wh_from in open_wh:
            for wh_to in open_wh:
                if wh_from == wh_to or (wh_from, wh_to) not in transfer_cost_dict:
                    continue
                transfer_flow[(wh_from, wh_to, gid)] = solver.NumVar(0, inf, f"t_{wh_from}_{wh_to}_{gid}")

    # tiered import cost: binary tier_active + tier_volume bounded to [min,max] x tier_active,
    # for each (supplier, wh) pair with stepped pricing and at least one open warehouse
    tier_active, tier_volume = {}, {}
    for (sid, wh_id), tiers in tiers_by_pair.items():
        if wh_id not in open_wh:
            continue
        for row in tiers:
            tier_id, hi = row["tier_id"], row["max_pallets"]
            hi_bound = hi if pd.notna(hi) else total_demand  # unbounded top tier -> network-wide cap
            tier_active[(sid, wh_id, tier_id)] = solver.BoolVar(f"ta_{sid}_{wh_id}_{tier_id}")
            tier_volume[(sid, wh_id, tier_id)] = solver.NumVar(0, hi_bound, f"tv_{sid}_{wh_id}_{tier_id}")

    # =========================================================================
    # Constraints
    # =========================================================================

    # demand satisfaction: every store-group fully served
    for dr in demand_recs:
        store_id, group_id, qty = dr["store_id"], dr["group_id"], dr["demand_pallets"]
        solver.Add(sum(dist_flow[(wh_id, store_id, group_id)] for wh_id in open_wh) == qty)

    # warehouse throughput capacity: outbound-to-store + outbound-transfer, which by flow
    # balance (below) equals total inbound — this is what actually caps a consolidation
    # hub's volume, not just what it ships directly to stores
    for wh_id in open_wh:
        cap = warehouses.loc[warehouses["wh_id"] == wh_id, "capacity_pallets"].iloc[0]
        outbound_terms = [dist_flow[(wh_id, s, g)] for s, g in store_groups]
        transfer_out_terms = [var for (wf, _, _), var in transfer_flow.items() if wf == wh_id]
        solver.Add(sum(outbound_terms) + sum(transfer_out_terms) <= cap)

    # flow balance per (wh, group): inbound + transfers-in == outbound-to-stores + transfers-out
    for wh_id in open_wh:
        for gid in groups:
            inbound_terms = [inbound_flow[(sid, wh_id, gid)]
                              for sid in eligible_suppliers_by_group.get(gid, [])
                              if (sid, wh_id, gid) in inbound_flow]
            transfer_in = [var for (_, wt, g), var in transfer_flow.items() if wt == wh_id and g == gid]
            transfer_out = [var for (wf, _, g), var in transfer_flow.items() if wf == wh_id and g == gid]
            outbound_terms = [dist_flow[(wh_id, s, g)] for s, g in store_groups if g == gid]
            solver.Add(sum(inbound_terms) + sum(transfer_in) == sum(outbound_terms) + sum(transfer_out))

    # supplier network-wide capacity cap, from supply_share
    for (sid, gid), cap in supplier_cap.items():
        terms = [inbound_flow[(sid, wh_id, gid)] for wh_id in open_wh if (sid, wh_id, gid) in inbound_flow]
        if terms:
            solver.Add(sum(terms) <= cap)

    # tier selection: at most one tier active per (supplier, wh); tier_volume bounded by
    # [min,max] x tier_active; total tier_volume == total import volume for that pair
    for (sid, wh_id), tiers in tiers_by_pair.items():
        if wh_id not in open_wh:
            continue
        solver.Add(sum(tier_active[(sid, wh_id, row["tier_id"])] for row in tiers) <= 1)
        for row in tiers:
            tier_id, lo, hi = row["tier_id"], row["min_pallets"], row["max_pallets"]
            hi_bound = hi if pd.notna(hi) else total_demand
            solver.Add(tier_volume[(sid, wh_id, tier_id)] >= lo * tier_active[(sid, wh_id, tier_id)])
            solver.Add(tier_volume[(sid, wh_id, tier_id)] <= hi_bound * tier_active[(sid, wh_id, tier_id)])
        total_import = sum(inbound_flow[(sid, wh_id, gid)] for gid in groups if (sid, wh_id, gid) in inbound_flow)
        solver.Add(sum(tier_volume[(sid, wh_id, row["tier_id"])] for row in tiers) == total_import)

    # =========================================================================
    # Objective: delivery + inbound (flat or tiered) + transfer + handling + fixed
    # =========================================================================

    cost_terms = []

    for wh_id in open_wh:
        for s, g in store_groups:
            unit_cost = delivery_cost_dict.get((wh_id, s), 0)
            if unit_cost:
                cost_terms.append(unit_cost * dist_flow[(wh_id, s, g)])

    for (sid, wh_id, gid), var in inbound_flow.items():
        if (sid, wh_id) in tiers_by_pair:
            continue  # costed via tier_volume below instead
        cost_terms.append(inbound_cost_dict.get((sid, wh_id), 0) * var)

    for (sid, wh_id), tiers in tiers_by_pair.items():
        if wh_id not in open_wh:
            continue
        for row in tiers:
            cost_terms.append(row["cost_per_pallet_eur"] * tier_volume[(sid, wh_id, row["tier_id"])])

    for (wf, wt, gid), var in transfer_flow.items():
        cost_terms.append(transfer_cost_dict.get((wf, wt), 0) * var)

    # handling: one touch per pallet shipped to a store (dist_flow) PLUS one extra touch
    # per pallet shipped onward as a transfer (at the origin hub) — a transferred pallet
    # is handled twice (hub + destination) vs once for a direct flow, so consolidation
    # has a real handling cost trade-off against the cheaper import tier
    for wh_id in open_wh:
        h = handling_cost.get(wh_id, 0)
        for s, g in store_groups:
            cost_terms.append(h * dist_flow[(wh_id, s, g)])
        for (wf, wt, gid), var in transfer_flow.items():
            if wf == wh_id:
                cost_terms.append(h * var)

    fixed_total = warehouses[warehouses["wh_id"].isin(open_wh)]["fixed_cost_eur_per_month"].sum()

    solver.Minimize(solver.Sum(cost_terms))
    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return {"feasible": False, "reason": "Solver could not find an optimal solution."}

    # =========================================================================
    # Extract results
    # =========================================================================

    dist_rows = [(wh_id, s, g, var.solution_value())
                 for (wh_id, s, g), var in dist_flow.items() if var.solution_value() > 1e-6]
    flows_detail = pd.DataFrame(dist_rows, columns=["wh_id", "store_id", "group_id", "pallets"])
    flows = flows_detail.groupby(["wh_id", "store_id"], as_index=False)["pallets"].sum() \
        if not flows_detail.empty else pd.DataFrame(columns=["wh_id", "store_id", "pallets"])

    if not flows_detail.empty:
        flows_detail["days_to_serve"] = list(map(days_to_serve_dict.get,
                                                   zip(flows_detail.wh_id, flows_detail.store_id)))
        flows_detail["delivery_unit_cost"] = list(map(delivery_cost_dict.get,
                                                        zip(flows_detail.wh_id, flows_detail.store_id)))
        flows_detail["handling_unit_cost"] = flows_detail["wh_id"].map(handling_cost)

    src_rows = [(sid, wh_id, g, var.solution_value())
                for (sid, wh_id, g), var in inbound_flow.items() if var.solution_value() > 1e-6]
    sourcing_detail = pd.DataFrame(src_rows, columns=["supplier_id", "wh_id", "group_id", "pallets"])
    if not sourcing_detail.empty:
        sourcing_detail["tiered"] = [(sid, wh_id) in tiers_by_pair
                                      for sid, wh_id in zip(sourcing_detail.supplier_id, sourcing_detail.wh_id)]
        sourcing_detail["flat_unit_cost"] = list(map(inbound_cost_dict.get,
                                                       zip(sourcing_detail.supplier_id, sourcing_detail.wh_id)))

    xfer_rows = [(wf, wt, g, var.solution_value())
                 for (wf, wt, g), var in transfer_flow.items() if var.solution_value() > 1e-6]
    transfer_detail = pd.DataFrame(xfer_rows, columns=["wh_id_from", "wh_id_to", "group_id", "pallets"])
    if not transfer_detail.empty:
        transfer_detail["unit_cost"] = list(map(transfer_cost_dict.get,
                                                  zip(transfer_detail.wh_id_from, transfer_detail.wh_id_to)))

    delivery_total = (flows_detail["pallets"] * flows_detail["delivery_unit_cost"]).sum() \
        if not flows_detail.empty else 0.0

    inbound_total = 0.0
    if not sourcing_detail.empty:
        flat_mask = ~sourcing_detail["tiered"]
        inbound_total += (sourcing_detail.loc[flat_mask, "pallets"] * sourcing_detail.loc[flat_mask, "flat_unit_cost"]).sum()
    for (sid, wh_id), tiers in tiers_by_pair.items():
        if wh_id not in open_wh:
            continue
        for row in tiers:
            inbound_total += row["cost_per_pallet_eur"] * tier_volume[(sid, wh_id, row["tier_id"])].solution_value()

    transfer_total = (transfer_detail["pallets"] * transfer_detail["unit_cost"]).sum() \
        if not transfer_detail.empty else 0.0

    handling_total = (flows_detail["pallets"] * flows_detail["handling_unit_cost"]).sum() \
        if not flows_detail.empty else 0.0
    if not transfer_detail.empty:
        transfer_handling_rate = transfer_detail["wh_id_from"].map(handling_cost)
        handling_total += (transfer_detail["pallets"] * transfer_handling_rate).sum()

    total_pallets = flows_detail["pallets"].sum() if not flows_detail.empty else 0
    weighted_days = ((flows_detail["pallets"] * flows_detail["days_to_serve"]).sum() / total_pallets
                      if total_pallets else 0)

    return {
        "feasible": True,
        "flows": flows,                    # aggregated wh_id/store_id/pallets — for map/dashboard
        "flows_detail": flows_detail,       # wh_id/store_id/group_id/pallets — for deeper inspection
        "sourcing_detail": sourcing_detail, # supplier_id/wh_id/group_id/pallets — solver-chosen sourcing
        "transfer_detail": transfer_detail, # wh_id_from/wh_id_to/group_id/pallets — internal transfers
        "delivery_cost_eur": round(delivery_total, 0),
        "inbound_cost_eur": round(inbound_total, 0),
        "transfer_cost_eur": round(transfer_total, 0),
        "handling_cost_eur": round(handling_total, 0),
        "fixed_cost_eur": round(fixed_total, 0),
        "total_cost_eur": round(delivery_total + inbound_total + transfer_total + handling_total + fixed_total, 0),
        "avg_days_to_serve": round(weighted_days, 2),
        "open_wh_count": len(open_wh),
    }
