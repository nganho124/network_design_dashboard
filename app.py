"""
AI Supply Chain Network Advisor — main entry point.

Layout: 2 tabs (Map / Dashboard) + a sidebar for scenario management
(solve / save / pick a saved scenario, and a natural-language chat that
does the same thing via Claude tool use — see scenario_chat_sidebar()).
"""

import pandas as pd
import streamlit as st

import chat_assistant
import db
import greenfield
from solver import solve_network
from state import init_session_state, update_scenario, next_new_warehouse_id
from components.map_view import render_map_tab
from components.dashboard_view import render_dashboard_tab

st.set_page_config(page_title="AI Network Assistant", 
                   layout="wide",
                   page_icon="🚚")

init_session_state()
with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

LIVE_OPTION = "__live__"  # sentinel for "current, unsaved edits" in the scenario picker


def _format_patch_summary(patch: dict, warehouses_df) -> str:
    wh_names = warehouses_df.set_index("wh_id")["wh_name"].to_dict()
    parts = [f"{wh_names.get(wh, wh)} → {status}" for wh, status in patch.get("wh_status", {}).items()]

    forced = patch.get("forced_allocation", [])
    if forced:
        # group by (group_id, wh_id) so "reassign 40 stores" reads as one line, not 40
        by_target = {}
        for row in forced:
            by_target.setdefault((row["group_id"], row["wh_id"]), []).append(row["store_id"])
        for (group_id, wh_id), store_ids in by_target.items():
            group_note = "" if group_id == "ALL" else f" ({group_id})"
            parts.append(f"{len(store_ids)} store(s){group_note} forced to {wh_names.get(wh_id, wh_id)}")

    for nw in patch.get("new_warehouses", []):
        if nw.get("city"):
            parts.append(f"opened new warehouse '{nw['wh_name']}' ({nw['wh_id']}) in {nw['city']}")

    return ", ".join(parts)


def _effective_reference_tables():
    """
    Expands scenario["new_warehouses"] into the tables solve_network() needs,
    generating each greenfield site's cost rows on the fly (greenfield.py) —
    st.session_state's own reference tables stay untouched (scenario-only,
    see state.py's docstring). Returns (warehouses, delivery_cost,
    inbound_cost, transfer_cost, inbound_cost_tiers). May raise ValueError
    (e.g. an unrecognized city) — callers should treat that as an infeasible
    scenario rather than letting it propagate as an unhandled exception.
    """
    warehouses = st.session_state.warehouses
    new_whs = st.session_state.scenario.get("new_warehouses", [])
    if not new_whs:
        return (warehouses, st.session_state.delivery_cost, st.session_state.inbound_cost,
                st.session_state.transfer_cost, st.session_state.inbound_cost_tiers)

    wh_rows = [warehouses]
    dc_rows, ic_rows, tc_rows, ict_rows = (
        [st.session_state.delivery_cost], [st.session_state.inbound_cost],
        [st.session_state.transfer_cost], [st.session_state.inbound_cost_tiers],
    )
    running_warehouses = warehouses
    for nw in new_whs:
        built = greenfield.build_new_warehouse(
            nw["city"], nw["wh_id"], nw["wh_name"],
            city_directory=st.session_state.city_directory, state_cost_index=st.session_state.state_cost_index,
            stores=st.session_state.stores, suppliers=st.session_state.suppliers, warehouses=running_warehouses,
        )
        new_row_df = pd.DataFrame([built["warehouse_row"]])
        wh_rows.append(new_row_df)
        dc_rows.append(built["delivery_cost"])
        ic_rows.append(built["inbound_cost"])
        tc_rows.append(built["transfer_cost"])
        ict_rows.append(built["inbound_cost_tiers"])
        running_warehouses = pd.concat([running_warehouses, new_row_df], ignore_index=True)

    return (
        pd.concat(wh_rows, ignore_index=True),
        pd.concat(dc_rows, ignore_index=True),
        pd.concat(ic_rows, ignore_index=True),
        pd.concat(tc_rows, ignore_index=True),
        pd.concat(ict_rows, ignore_index=True),
    )


def scenario_chat_sidebar():
    """
    Natural-language alternative to toggling warehouses by hand: describe a
    change (e.g. "close the Hamburg warehouse"), Claude proposes a scenario
    patch via tool use (chat_assistant.interpret_message), we apply it with
    update_scenario() and — if "Auto-solve" is on — solve it immediately.

    Claude never gets to claim a result itself; the message shown to the user
    is always built from the actual update_scenario()/solve_network() outcome.
    """
    st.sidebar.subheader("💬 Scenario Assistant")
    auto_solve = st.sidebar.checkbox(
        "Auto-solve after each change", value=False,
        help="Off: the chat only stages the change — review it and click 'Solve current "
             "scenario' yourself. On: it solves immediately after applying it (~15-20s).")

    for msg in st.session_state.chat_history:
        with st.sidebar.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.sidebar.chat_input("e.g. 'Close WH004 Cologne'")
    if not user_msg:
        return

    st.session_state.chat_history.append({"role": "user", "content": user_msg})
    existing_new_wh_ids = {nw["wh_id"] for nw in st.session_state.scenario.get("new_warehouses", [])} \
        | set(st.session_state.warehouses["wh_id"])
    result = chat_assistant.interpret_message(
        user_msg, st.session_state.chat_history[:-1],
        st.session_state.warehouses, st.session_state.scenario["wh_status"],
        st.session_state.delivery_baseline_share, st.session_state.city_directory, existing_new_wh_ids,
    )

    if result["error"]:
        reply = f"⚠️ {result['error']}"
    else:
        reply_parts = [result["reply"]] if result["reply"] else []
        if result["patch"]:
            update_scenario(result["patch"])
            reply_parts.append(f"Applied: {_format_patch_summary(result['patch'], st.session_state.warehouses)}.")
            if auto_solve:
                _solve_current_scenario()
                res = st.session_state.results
                if res.get("feasible"):
                    reply_parts.append(f"✅ Solved — total cost €{res['total_cost_eur']:,.0f}/mo.")
                else:
                    reply_parts.append(f"⚠️ Infeasible: {res.get('reason', 'no feasible solution.')}")
            else:
                reply_parts.append("Click **▶️ Solve current scenario** below to run it.")
        reply = " ".join(reply_parts) if reply_parts else "Sorry, I didn't catch a scenario change in that — could you rephrase?"

    st.session_state.chat_history.append({"role": "assistant", "content": reply})
    st.rerun()


def _solve_current_scenario():
    with st.spinner("Solving scenario..."):
        try:
            warehouses, delivery_cost, inbound_cost, transfer_cost, inbound_cost_tiers = _effective_reference_tables()
        except ValueError as e:
            st.session_state.results = {"feasible": False, "reason": str(e)}
            st.session_state.active_scenario_id = None
            return
        results = solve_network(
            st.session_state.scenario,
            warehouses,
            st.session_state.stores,
            st.session_state.demand,
            delivery_cost,
            inbound_cost,
            st.session_state.supply_share,
            inbound_cost_tiers,
            transfer_cost,
            st.session_state.scenario.get("forced_allocation", []),
            200
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
            # scenarios saved before these existed
            st.session_state.scenario.setdefault("forced_allocation", [])
            st.session_state.scenario.setdefault("new_warehouses", [])
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


# def new_warehouse_sidebar():
#     """
#     Test opening a brand-new ("greenfield") warehouse at any known city —
#     no pre-set capacity; the solver sizes it to whatever throughput is
#     actually worth routing there (see solver.py, greenfield.py). Scenario-only
#     (state.py's new_warehouses): doesn't touch the permanent reference data.
#     """
#     st.sidebar.subheader("🏗️ Add a new warehouse")

#     existing_ids = set(st.session_state.warehouses["wh_id"]) | {
#         nw["wh_id"] for nw in st.session_state.scenario.get("new_warehouses", [])
#     }
#     cities = sorted(st.session_state.city_directory["city"].tolist())

#     with st.sidebar.form("add_warehouse_form", clear_on_submit=True):
#         city = st.selectbox("City", cities, index=None, placeholder="Pick a city...", key="new_wh_city_select")
#         name = st.text_input("Warehouse name", placeholder="e.g. New WH Frankfurt", key="new_wh_name_input")
#         submitted = st.form_submit_button("Add warehouse", use_container_width=True)

#     if submitted:
#         if not city:
#             st.sidebar.warning("Pick a city first.")
#         else:
#             wh_id = next_new_warehouse_id(existing_ids)
#             wh_name = name.strip() or f"New WH {city}"
#             update_scenario({
#                 "new_warehouses": [{"wh_id": wh_id, "wh_name": wh_name, "city": city}],
#                 "wh_status": {wh_id: "open"},
#             })
#             st.rerun()

#     new_whs = st.session_state.scenario.get("new_warehouses", [])
#     if new_whs:
#         st.sidebar.caption("Greenfield sites in this scenario:")
#         for nw in new_whs:
#             status = st.session_state.scenario["wh_status"].get(nw["wh_id"], "open")
#             st.sidebar.caption(f"• {nw['wh_name']} ({nw['city']}) — {status}")


def main():
    st.title("🚚 AI Network Assistant")
    st.caption("Test different network setups before committing to a real restructuring decision.")

    scenario_chat_sidebar()
    scenario_library_sidebar()
    # new_warehouse_sidebar()

    with st.sidebar:
        st.subheader("Warehouse status")
        wh_status = st.session_state.scenario["wh_status"]
        open_count = sum(1 for s in wh_status.values() if s == "open")
        st.metric("Open warehouses", f"{open_count} / {len(wh_status)}")
        # st.caption("Toggle warehouses from the map tab's 'Adjust network manually' panel, "
        #            "then Solve to see the reallocated network.")

    tab1, tab2 = st.tabs(["🗺️ Network Map", "📊 Dashboard"])
    with tab1:
        render_map_tab()
    with tab2:
        render_dashboard_tab()


if __name__ == "__main__":
    main()
