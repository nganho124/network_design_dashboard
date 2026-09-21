# AI Supply Chain Network Advisor

A Streamlit app for exploring "what-if" supply chain network scenarios
(which warehouses to keep open, where to add a new one, how to route
stores) for a synthetic Germany DIY/furniture retail network — with a
Claude-powered chat that can propose scenario changes in natural language.

## Structure

```
network_design_dashboard/
├── app.py                       # Entry point: layout, tabs, sidebar (scenario library + chat)
├── state.py                     # Scenario schema + session_state helpers (single source of truth)
├── solver.py                    # OR-Tools network flow model (solve_network)
├── chat_assistant.py            # Natural language -> scenario patch, via Claude tool use
├── greenfield.py                # Cost/geometry generation for new (not-yet-built) warehouses
├── db.py                        # Persistence: reference data (parquet) + saved scenarios (SQLite)
├── generate_germany_data.py     # Synthetic reference data generator
├── styles.css                   # App styling
├── components/
│   ├── map_view.py              # Tab 1: folium map of the network
│   └── dashboard_view.py        # Tab 2: KPI dashboard (cost/service charts)
├── util/                        # Calculation and chart helpers used by dashboard_view.py
├── data/
│   ├── reference/                # Generated reference data (parquet) — warehouses, stores, costs, etc.
│   ├── assets/                   # Icons used on the map
│   └── scenarios.db              # Saved scenarios (SQLite)
└── requirements.txt
```

## Design principle: single source of truth

Everything reads and writes through `st.session_state.scenario` (the inputs)
and `st.session_state.results` (the solver output). The map tab, dashboard
tab, and chat assistant all talk to this ONE object — nothing talks to
anything else directly.

```
scenario (dict)  →  solve_network()  →  results (dict)
     ↑                                        ↓
[map clicks / manual edits]           [map render, dashboard render]
[chat message → scenario patch]
```

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Reference data is generated once and cached under `data/reference/`. To
regenerate it (e.g. after changing the data model):

```bash
python generate_germany_data.py
```
