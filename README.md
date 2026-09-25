# Iran – US – Israel Conflict Simulation (Sept 2026)

Multi-agent geopolitical simulation: **LLM agents** stay in character and
generate statements/strategy; **Jev** — a fast "System 1" typed decision
layer — runs every round and never writes prose. Jev only returns typed
answers:

| Question                                   | Type   |
|--------------------------------------------|--------|
| Who acts next?                             | choice |
| May this agent escalate militarily?        | noul   |
| P(full-scale war, next 72h)                | score  |
| P(deal / ceasefire, next 7d)               | score  |
| P(Iranian economic collapse accelerates)   | score  |
| Is the oil price reaction realistic?       | noul   |
| Does this action need human review?        | noul   |

## Architecture

```
SituationState ──> Jev (typed gates + probabilities)
       │                    │ decides acting order + escalation gates
       ▼                    ▼
   8 LLM agents ──> AgentActions ──> world-update rules ──> new state
       ▲
   X/Twitter feed (seeded per round; agents must cite a post by @handle)
```

- `jev/` — decision layer. `JevClient` asks narrow questions over HTTP to a
  small local model (default `llama3.2:3b`), parses the JSON answer into a
  typed `JevAnswer`, and falls back to a deterministic heuristic if the model
  returns garbage (flagged `[fallback]` in the transcript).
- `agents/` — personas (Trump, Netanyahu, IRGC/Mojtaba, Iranian people, EU,
  oil market, US voters, Iran sentiment tracker) + the Ollama-backed agent
  wrapper.
- `simulation/` — `state.py` (SituationState), `xfeed.py` (posts),
  `world.py` (Brent fair-value model + state drift), `director.py` (round loop).
- `ollama_client.py` — stdlib-only Ollama chat client. No third-party deps.

## Requirements

- Python 3.10+
- Running Ollama with the configured models, e.g.:

```bash
ollama pull llama3.2:3b          # Jev
ollama pull qwen35-uncensored    # default agent model
```

Model assignments live in `config.py` (env overrides: `SIM_JEV_MODEL`,
`SIM_AGENT_MODEL`, `SIM_FAST_MODEL`, `OLLAMA_HOST`).

## Run

```bash
python3 main.py                  # Round 1: 25–26 Sept 2026
python3 main.py --rounds 5       # keep simulating; state carries forward
python3 main.py --fast           # all agents on llama3.2:3b (quickest)
python3 main.py --offline        # no LLM calls — heuristic Jev + stub agents
python3 main.py --dump out.json  # save every Jev verdict + state to JSON
```

## Steer the simulation

- Seed new X posts in `simulation/xfeed.py` (`ROUND_POSTS[2]`, `[3]`, …) —
  agents cite them and the market reacts to them.
- Edit `simulation/world.py` to change how actions move oil, protests, and
  war intensity.
- Jev's question text lives in `jev/client.py`; tighten or add questions there.
