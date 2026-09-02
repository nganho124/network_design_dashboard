"""
Persistence layer.

- Reference/static data (warehouses, stores, suppliers, product_groups,
  demand, supply_baseline_share, delivery_baseline_share, supply_share,
  inbound_cost, inbound_cost_tiers, delivery_cost, transfer_cost) ->
  Parquet files under data/reference/. This is "today's known world" —
  generated once per industry choice, rarely touched after that.

- Scenario data (each what-if test: which WHs are open, delivery mode,
  resulting cost/service metrics, and the detailed flow table) -> SQLite
  at data/scenarios.db. You'll create many of these live at the hackathon,
  including ones written by the AI chat — SQLite gives you real querying
  (filter/sort/compare) instead of hunting through loose CSV files, and
  it's a single file you can open in DB Browser for SQLite to validate.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
REFERENCE_DIR = DATA_DIR / "reference"
DB_PATH = DATA_DIR / "scenarios.db"


def init_storage():
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scenarios (
            scenario_id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            source TEXT,               -- 'manual' or 'ai_chat'
            scenario_patch TEXT,       -- JSON: e.g. wh_status / delivery_mode changes
            feasible INTEGER,
            total_cost_eur REAL,
            avg_days_to_serve REAL,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scenario_flows (
            scenario_id TEXT,
            wh_id TEXT,
            store_id TEXT,
            pallets REAL,
            FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Reference data — static per industry/network configuration
# ---------------------------------------------------------------------------

def save_reference_data(data: dict):
    """data: dict of {table_name: DataFrame}, e.g. output of build_all_data().

    Full replace: clears any existing .parquet files first, so a table that
    was renamed or removed doesn't linger as a stale file alongside the new
    ones.
    """
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in REFERENCE_DIR.glob("*.parquet"):
        stale.unlink()
    for name, df in data.items():
        df.to_parquet(REFERENCE_DIR / f"{name}.parquet", index=False)


def load_reference_data() -> dict:
    return {p.stem: pd.read_parquet(p) for p in REFERENCE_DIR.glob("*.parquet")}


# ---------------------------------------------------------------------------
# Scenario data — one row per what-if test, queryable and comparable
# ---------------------------------------------------------------------------

def save_scenario(name: str, scenario_patch: dict, results: dict,
                   description: str = "", source: str = "manual") -> str:
    """results: solve_network() output. Only the aggregated wh_id/store_id/pallets
    "flows" table is persisted (what map_view.py needs to redraw the network) —
    the richer per-group/sourcing/transfer breakdown isn't kept across a save/load
    round trip."""
    scenario_id = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?)",
        (scenario_id, name, description, source, json.dumps(scenario_patch),
         int(bool(results.get("feasible", False))), results.get("total_cost_eur"),
         results.get("avg_days_to_serve"), datetime.now(timezone.utc).isoformat()),
    )
    flows = results.get("flows")
    if results.get("feasible") and flows is not None and not flows.empty:
        flows = flows.copy()
        flows["scenario_id"] = scenario_id
        keep_cols = [c for c in ["scenario_id", "wh_id", "store_id", "pallets"] if c in flows.columns]
        flows[keep_cols].to_sql("scenario_flows", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()
    return scenario_id


def load_scenario(scenario_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    row = pd.read_sql("SELECT * FROM scenarios WHERE scenario_id = ?", conn, params=(scenario_id,))
    flows = pd.read_sql("SELECT * FROM scenario_flows WHERE scenario_id = ?", conn, params=(scenario_id,))
    conn.close()
    if row.empty:
        return None
    record = row.iloc[0].to_dict()
    record["scenario_patch"] = json.loads(record["scenario_patch"])
    record["flows"] = flows
    return record


def list_scenarios() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT scenario_id, name, source, feasible, total_cost_eur, "
        "avg_days_to_serve, created_at FROM scenarios ORDER BY created_at DESC", conn)
    conn.close()
    return df