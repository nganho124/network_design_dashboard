# AI Supply Chain Network Advisor — Scaffold

## Structure

```
supply_chain_advisor/
├── app.py                     # Entry point: layout, tabs, session_state init
├── state.py                   # Scenario schema + session_state helpers
├── data.py                    # Synthetic/sample data generation
├── solver.py                  # OR-Tools network flow model (solve_network)
├── components/
│   ├── map_view.py             # Tab 1: folium map of the network
│   └── dashboard_view.py       # Tab 2: plotly cost/service charts
└── requirements.txt
```

## Design principle: single source of truth

Everything reads and writes through `st.session_state.scenario` (the inputs)
and `st.session_state.results` (the solver output). Map tab, dashboard tab,
and — later — the chatbot all talk to this ONE object. Nothing talks to
anything else directly.

```
scenario (dict)  →  solve_network()  →  results (dict)
     ↑                                        ↓
[map clicks]                          [map render, dashboard render]
[chat message]  (added at hackathon)
```

## Why this matters for the hackathon night

`solve_network(scenario) -> results` is a pure function with a typed input/output.
When you add Claude on the night, the ONLY new code is:

1. A tool/function-call schema that mirrors the `scenario` dict fields (see `state.py`)
2. A parser step: user message → partial scenario update → merge into `st.session_state.scenario`
3. Re-run `solve_network()` and re-render — same as any manual edit

No architecture changes needed. This is the whole point of building it this way now.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```
