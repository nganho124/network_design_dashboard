"""
AI Scenario Assistant — natural language -> scenario patch, via Claude tool use.

Single-call pattern (no agentic loop): send the user's message plus a system
prompt describing the current network (warehouse ids/names/current status)
and one tool (update_scenario), with tool_choice left at the default "auto".
Claude's response may contain a text block (a clarifying question), a
tool_use block (the proposed patch), or both.

Claude never reports success/failure itself — it only proposes a patch. The
caller (app.py) applies it via state.update_scenario() and runs
solve_network() to get the real outcome, then builds the user-facing message
from that. This keeps the solver as the single source of truth for whether a
scenario actually works, instead of trusting the model's guess.
"""

import anthropic
import streamlit as st

MODEL = "claude-opus-5"

UPDATE_SCENARIO_TOOL = {
    "name": "update_scenario",
    "description": (
        "Apply a partial update to the network scenario — currently just which "
        "warehouses are open or closed. Only include warehouses whose status "
        "should actually change; omit warehouses that stay as they are."
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


@st.cache_resource(show_spinner=False)
def _get_client():
    return anthropic.Anthropic()


def _build_system_prompt(warehouses_df, wh_status: dict) -> str:
    lines = [
        "You are a scenario assistant for a supply chain network design tool "
        "(DIY/home-improvement retail, Germany). The user describes network "
        "changes in plain language (e.g. 'close the Hamburg warehouse', "
        "'reopen WH004') and you translate that into a call to the "
        "update_scenario tool using the exact warehouse_id.",
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
        "- Only call update_scenario when you're confident which warehouse(s) and status "
        "the user means. If the request is ambiguous, references a warehouse not in the "
        "list, or isn't about warehouse status, ask a short clarifying question instead "
        "of guessing — don't call the tool in that case.",
        "- Don't claim the change has been solved or that it succeeded — the app applies "
        "your patch and reports the real result separately.",
        "- Keep replies to one short sentence.",
    ]
    return "\n".join(lines)


def interpret_message(user_message: str, chat_history: list, warehouses_df, wh_status: dict) -> dict:
    """
    Returns {"reply": str | None, "patch": dict | None, "error": str | None}.

    `patch` is a partial scenario dict ready for state.update_scenario() —
    already filtered to known warehouse ids and valid statuses, so it's safe
    to apply without re-validating.
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
            tools=[UPDATE_SCENARIO_TOOL],
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

    reply_text = " ".join(b.text for b in response.content if b.type == "text").strip() or None

    patch = None
    valid_wh_ids = set(warehouses_df["wh_id"])
    for block in response.content:
        if block.type == "tool_use" and block.name == "update_scenario":
            raw_status = block.input.get("wh_status", {})
            cleaned = {wh: status for wh, status in raw_status.items()
                       if wh in valid_wh_ids and status in ("open", "closed")}
            if cleaned:
                patch = {"wh_status": cleaned}
            break

    return {"reply": reply_text, "patch": patch, "error": None}