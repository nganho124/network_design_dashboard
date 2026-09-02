"""
AI Scenario Assistant — natural language -> scenario patch, via Claude tool use.

Single-call pattern (no agentic loop): send the user's message plus a system
prompt describing the current network (warehouse ids/names/current status)
and two tools (update_scenario, reassign_stores), with tool_choice left at
the default "auto". Claude's response may contain a text block (a clarifying
question), one or more tool_use blocks (it can call both tools in one turn,
e.g. "close Berlin and move its stores to Hamburg"), or both.

reassign_stores never needs Claude to know individual store ids (there are
400 of them — far too many to list in every prompt) — it just names a
from/to warehouse pair, and _stores_for_warehouse() resolves which stores
that covers in Python, from each store's PRIMARY warehouse in
delivery_baseline_share (its highest-share WH).

Claude never reports success/failure itself — it only proposes a patch. The
caller (app.py) applies it via state.update_scenario() and runs
solve_network() to get the real outcome, then builds the user-facing message
from that. This keeps the solver as the single source of truth for whether a
scenario actually works, instead of trusting the model's guess.
"""

import anthropic
import streamlit as st

from state import next_new_warehouse_id

MODEL = "claude-opus-5"

UPDATE_SCENARIO_TOOL = {
    "name": "update_scenario",
    "description": (
        "Apply a partial update to the network scenario — which warehouses are open "
        "or closed. Only include warehouses whose status should actually change; omit "
        "warehouses that stay as they are."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "wh_status": {
                "type": "object",
                "description": "Mapping of warehouse_id (e.g. 'WH001') -> 'open' or 'closed'.",
                "additionalProperties": {"type": "string", "enum": ["open", "closed"]},
            },
        },
        "required": ["wh_status"],
    },
}

REASSIGN_STORES_TOOL = {
    "name": "reassign_stores",
    "description": (
        "Force every store currently primarily served by one warehouse to be served "
        "only by a different warehouse instead of leaving that free for the solver to "
        "optimize — e.g. 'move Berlin's stores to Hamburg' when closing Berlin. You do "
        "NOT need to know individual store ids; this resolves them automatically from "
        "which warehouse currently serves each store. Use group_id='ALL' unless the "
        "user names a specific product group."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "from_wh_id": {"type": "string", "description": "Warehouse currently serving the stores to move."},
            "to_wh_id": {"type": "string", "description": "Warehouse the stores should be forced onto."},
            "group_id": {"type": "string", "description": "Product group id, or 'ALL' for every group."},
        },
        "required": ["from_wh_id", "to_wh_id", "group_id"],
    },
}

OPEN_NEW_WAREHOUSE_TOOL = {
    "name": "open_new_warehouse",
    "description": (
        "Test opening a brand-new, not-yet-built warehouse at a city that isn't already "
        "one of the existing warehouses. It has no pre-set capacity — the solver sizes it "
        "to whatever throughput is actually worth routing there, so you don't need to "
        "guess a capacity number. It opens immediately (wh_status='open'). Note: you can't "
        "reference the new warehouse's id in the SAME turn (e.g. to reassign stores onto "
        "it) since it's only assigned after this call — do that as a follow-up message "
        "once you see its id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City to place the new warehouse in."},
            "wh_name": {"type": "string", "description": "Display name, e.g. 'New WH Frankfurt'."},
        },
        "required": ["city", "wh_name"],
    },
}


@st.cache_resource(show_spinner=False)
def _get_client():
    return anthropic.Anthropic()


def _build_system_prompt(warehouses_df, wh_status: dict) -> str:
    lines = [
        "You are a scenario assistant for a supply chain network design tool "
        "(DIY/home-improvement retail, Germany). The user describes network "
        "changes in plain language and you translate that into tool calls using "
        "exact warehouse_ids.",
        "",
        "Warehouses (id — name, city, current status):",
    ]
    for _, wh in warehouses_df.iterrows():
        status = wh_status.get(wh["wh_id"], "open")
        lines.append(f"- {wh['wh_id']} — {wh['wh_name']} ({wh['city']}), currently {status}")
    lines += [
        "",
        "Rules:",
        "- Resolve city or warehouse names to the exact warehouse_id from the list above.",
        "- Use update_scenario for opening/closing EXISTING warehouses, reassign_stores for "
        "forcing one warehouse's stores onto another, and open_new_warehouse to test a "
        "brand-new site at a city not already in the list above (any real German city — "
        "you don't need a fixed list, the app validates it and will tell you if it's not "
        "recognized). A single request can need multiple tools (e.g. 'close Berlin and "
        "move its stores to Hamburg' = update_scenario closing WH002 + reassign_stores "
        "WH002->WH001) — call all the tools that apply in the same turn.",
        "- Only call a tool when you're confident which warehouse(s)/city the user means. "
        "If the request is ambiguous, references an existing warehouse not in the list, or "
        "isn't about warehouse status/reassignment/opening a new site, ask a short "
        "clarifying question instead of guessing — don't call a tool in that case.",
        "- Don't claim the change has been solved or that it succeeded — the app applies "
        "your patch and reports the real result separately.",
        "- Keep replies to one short sentence.",
    ]
    return "\n".join(lines)


def _stores_for_warehouse(delivery_baseline_share, wh_id: str) -> list:
    """Store ids whose PRIMARY warehouse (highest average volume_share) is wh_id."""
    by_store_wh = delivery_baseline_share.groupby(["store_id", "wh_id"])["volume_share"].mean().reset_index()
    primary = by_store_wh.loc[by_store_wh.groupby("store_id")["volume_share"].idxmax()]
    return primary.loc[primary["wh_id"] == wh_id, "store_id"].tolist()


def interpret_message(user_message: str, chat_history: list, warehouses_df, wh_status: dict,
                       delivery_baseline_share, city_directory, existing_new_wh_ids: set) -> dict:
    """
    Returns {"reply": str | None, "patch": dict | None, "error": str | None}.

    `patch` is a partial scenario dict ready for state.update_scenario() —
    wh_status keys, forced_allocation rows, and new_warehouses rows are
    already filtered/resolved against known ids, so it's safe to apply
    without re-validating. `existing_new_wh_ids` should be every warehouse id
    already in use (existing + already-added greenfield ones this scenario),
    so a newly opened warehouse gets a fresh id.
    """
    try:
        client = _get_client()
        messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"effort": "low"},  # simple slot-filling task, doesn't need deep reasoning
            system=_build_system_prompt(warehouses_df, wh_status),
            tools=[UPDATE_SCENARIO_TOOL, REASSIGN_STORES_TOOL, OPEN_NEW_WAREHOUSE_TOOL],
            messages=messages,
        )
    except anthropic.AuthenticationError:
        return {"reply": None, "patch": None,
                "error": "Anthropic API key missing or invalid — set ANTHROPIC_API_KEY and restart the app."}
    except anthropic.RateLimitError:
        return {"reply": None, "patch": None, "error": "Rate limited by the Anthropic API — try again shortly."}
    except anthropic.APIConnectionError:
        return {"reply": None, "patch": None, "error": "Couldn't reach the Anthropic API — check your connection."}
    except anthropic.APIStatusError as e:
        return {"reply": None, "patch": None, "error": f"Anthropic API error: {e.message}"}

    reply_notes = [b.text for b in response.content if b.type == "text" and b.text.strip()]

    valid_wh_ids = set(warehouses_df["wh_id"])
    wh_status_patch = {}
    forced_allocation_patch = []
    new_warehouses_patch = []
    known_cities = set(city_directory["city"].str.lower())
    used_ids = set(existing_new_wh_ids)

    for block in response.content:
        if block.type != "tool_use":
            continue

        if block.name == "update_scenario":
            raw_status = block.input.get("wh_status", {})
            wh_status_patch.update({wh: status for wh, status in raw_status.items()
                                     if wh in valid_wh_ids and status in ("open", "closed")})

        elif block.name == "reassign_stores":
            from_wh, to_wh, group_id = block.input.get("from_wh_id"), block.input.get("to_wh_id"), block.input.get("group_id", "ALL")
            if from_wh in valid_wh_ids and to_wh in valid_wh_ids:
                store_ids = _stores_for_warehouse(delivery_baseline_share, from_wh)
                forced_allocation_patch.extend(
                    {"store_id": sid, "group_id": group_id, "wh_id": to_wh, "volume_share": None}
                    for sid in store_ids
                )

        elif block.name == "open_new_warehouse":
            city, wh_name = block.input.get("city", ""), block.input.get("wh_name", "")
            if city.strip().lower() not in known_cities:
                reply_notes.append(f"'{city}' isn't a city I recognize — try a different (larger) German city.")
            else:
                new_wh_id = next_new_warehouse_id(used_ids)
                used_ids.add(new_wh_id)
                new_warehouses_patch.append({"wh_id": new_wh_id, "wh_name": wh_name or f"New WH {city}", "city": city})
                wh_status_patch[new_wh_id] = "open"

    patch = {}
    if wh_status_patch:
        patch["wh_status"] = wh_status_patch
    if forced_allocation_patch:
        patch["forced_allocation"] = forced_allocation_patch
    if new_warehouses_patch:
        patch["new_warehouses"] = new_warehouses_patch

    reply_text = " ".join(reply_notes).strip() or None
    return {"reply": reply_text, "patch": patch or None, "error": None}
