# Iran – US – Israel Conflict Simulation (Sept 2026)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLMs-000000?logo=ollama&logoColor=white)](https://ollama.com)
[![Jev](https://img.shields.io/badge/Jev-typed%20decision%20layer-blueviolet)](jev/)
[![Jev model](https://img.shields.io/badge/decision%20model-llama3.2%3A3b-f7941d?logo=meta&logoColor=white)](https://ollama.com/library/llama3.2)
[![Agent model](https://img.shields.io/badge/agent%20model-qwen35--uncensored-c0392b)](https://ollama.com)
[![Charts](https://img.shields.io/badge/charts-matplotlib-11557c)](https://matplotlib.org)
[![Runs](https://img.shields.io/badge/runs-100%25%20local-success)](config.py)

A fully local multi-agent geopolitical simulation. Eight LLM agents play
state and non-state actors in a fictionalized September-2026 Iran–US–Israel
war; a fast typed decision layer called **Jev** governs who may act, who may
escalate, and how probable war / deal / collapse are — every single day.

The split is deliberate:

- **Agents (System 2, big models)** — stay strictly in character, write
  statements, strategy, and private reasoning. They never decide game
  mechanics.
- **Jev (System 1, small fast model)** — never writes prose. It only
  returns typed answers: a `choice` (who acts next), a `noul` (yes/no
  gate), or a `score` (calibrated probability 0–1).

## Scenario seed (25 September 2026)

- ~7 months into the war. Khamenei Sr. was killed early on; **Mojtaba
  Khamenei** is Supreme Leader, IRGC dominates the war cabinet.
- Trump at the UNGA framed a binary choice: a deal that lets Iran rebuild,
  or annihilation. Witkoff/Kushner met Iranian officials on the sidelines.
- Limited exchanges of fire continue. Brent ≈ $100. US midterms ~40 days
  out. Iran's economy is under blockade, ~60% inflation, rial ≈ 1.65M/USD.

## The stack — what runs what

| Component | Model (default) | Job |
|---|---|---|
| **Jev** decision layer | `llama3.2:3b` | typed gates + probabilities only; never prose |
| **Character agents** | `qwen35-uncensored` | in-character statements, strategy, midnight learning |
| **Oil market / IR street tracker** | `llama3.2:3b` | structured metric output |
| **Charts** | matplotlib + pillow | GIF animation + PNG boards |
| **Runtime** | stdlib HTTP → Ollama | zero third-party deps for the sim core |

Swap any model via env: `SIM_JEV_MODEL`, `SIM_AGENT_MODEL`,
`SIM_FAST_MODEL` (see `config.py`).

## The eight agents

| Agent | What drives it |
|---|---|
| **Donald Trump** | Look strong; midterms in ~40 days; gas prices down; a deal sold as total victory is ideal, but he will escalate if humiliated. |
| **Netanyahu** | Permanent elimination of Iran's nuclear capacity; maximum freedom of military action; will act alone to kill a bad deal. |
| **Iran hardliners** (IRGC + Mojtaba) | Regime survival; keep the 60% stockpile as insurance; weaponize oil/Hormuz leverage; outwait US domestic pain. |
| **Iranian people** | End the misery. Not a policy actor — the pressure cooker both regimes read. Loyalist-to-revolutionary range. |
| **European Union** | De-escalation above all; can't absorb another energy shock; offers escrow mechanisms, sanctions-relief architecture, venues. |
| **Oil market** | Pure price logic. Reads Hormuz status, tanker incidents, war intensity; always outputs `BRENT:` + `FORECAST:`. |
| **US public / midterm voters** | Cheap gas, no endless wars, no body bags — but a loud "finish the job" minority. Politicians read them. |
| **Iran sentiment tracker** | Street-level metrics: mood, protest level, war fatigue, nationalism rally, black market. Reports, never acts. |

## How one day runs

```
SituationState ──> Jev: who acts next?  ──loop──>  for each chosen agent:
                       │                            Jev: escalation permitted?  (noul)
                       │                            Jev: needs human review?    (noul)
                       │                            agent speaks (cites X posts)
                       │                            world nudges -> snapshot
                       ▼
              Jev scores: P(war 72h) · P(deal 7d) · P(collapse)
              oil settle: market call vs Jev realism check (fair-value override)
              MIDNIGHT LEARNING: ground truth -> agents reflect -> predictions
              render all charts -> checkpoint dump -> next day
```

Jev's seven questions per round:

| Question | Type | Used for |
|---|---|---|
| Who acts next? | `choice` | the acting order (or `end_round`) |
| Escalation permitted? | `noul` | per-agent military gate |
| P(full-scale war, 72h) | `score` | round verdict + history track |
| P(deal / ceasefire, 7d) | `score` | round verdict + history track |
| P(Iranian econ collapse) | `score` | round verdict + history track |
| Oil reaction realistic? | `noul` | if NO → fair-value model overrides the market call |
| Needs human review? | `noul` | flagged actions run under a "review hold" |

## The world model

`simulation/world.py` maps what agents *say and do* onto state variables:

- **Keyword-driven effects** — "strike/bomb/missile" raises war intensity;
  "hormuz/strait/tanker" raises incidents (and "close/shut/mine" flips
  Hormuz to `partially_closed`); "ceasefire/deal/framework/corridor"
  strengthens the diplomatic track and cools intensity; "sanction" raises
  economic pressure; "protest/bazaar shut" raises street pressure.
- **Oil** — `fair_brent = 82 + Hormuz_premium + 1.2·intensity + 2·incidents`.
  Premium: open $0, threatened $18, partially closed $35, closed $60.
  Intra-day, Brent drifts 30% toward fair value after every act; at settle,
  the market agent's call is blended 50/50 with fair value — unless Jev
  rules it unrealistic, in which case fair value wins outright.
  US gas ≈ `$3.10 + 0.024·(Brent − 70)`.
- **End-of-day drift** — economic pressure ratchets up, protests scale with
  it, regime cohesion decays, war support slides with pump prices.
- **Influence** — each act's own deltas on tracked metrics (war, protests,
  pressure, cohesion, gas, Brent) are summed into a per-agent influence
  score. Ambient market drift is deliberately *not* attributed, so the
  metric measures agency, not luck.

## The midnight learning cycle

After each day closes:

1. **Ground truth** — the day's actual state changes, the settled Brent,
   Jev's scores, plus the **real-world wire**: at midnight the sim fetches
   the actual Brent/WTI close (Yahoo Finance) and the day's top conflict
   headlines (Google News RSS) into `real_events/dayN.txt`, so agents grade
   their predictions against reality, not just the simulation. A
   hand-written `real_events/dayN.txt` always takes precedence if it
   already exists; if the fetch fails the day simply runs on simulated
   ground truth.
2. **Every agent reflects** (`Agent.learn`): gets the day's outcomes + its
   own prediction from last midnight, returns
   `LEARNED / BELIEF / STANCE / PREDICTION / P_WAR / P_DEAL / BRENT_DIR`.
3. **Memory persists** — last lessons + current stance are injected into
   the next day's prompt (`_memory_block`), so predictions made at night
   measurably change daytime behavior.
4. **Scorecard** — yesterday's `BRENT_DIR` call is graded against the real
   settle; each agent accumulates a W–L record.
5. Memories are written into `--dump` files; `--resume` (or a daemon
   restart) restores them, so agents keep what they learned.

## Generated artifacts (every day)

| File | Contents |
|---|---|
| `roundN_animation.gif` | Animated 4-panel build, one frame per agent act: Brent path, war intensity (✕ = Jev denied an escalation request, ★ = human-review flag), Iran street/regime, US domestic — plus an event ticker and Jev's closing scores. |
| `roundN_summary.png` | The final animation frame as a static chart. |
| `dayN_learning.png` | Midnight board: each agent's lesson, prediction, P_war/P_deal, Brent call, W–L scorecard — and today's influence ranking. |
| `dayN_predictions.png` | Focused predictions: per-agent P(war)/P(deal) bars, Brent direction glyph, predicted event text, Jev's scores as reference lines. |
| `dayN_before_after.png` | Dumbbell chart: last night's call (grey) vs. tonight's post-learning update (colored arrow) for P(war) and P(deal). |
| `sim_history.png` | Cumulative: Brent & gas across days (Hormuz-constrained days shaded red), the Jev war/deal/collapse probability track, cumulative agent influence. |

## CLI

```
python3 main.py [options]

--rounds N      simulate N days in one process (state carries forward)
--resume FILE   continue from a --dump file (world + memories + history)
--daemon        stay resident; run one day at every 00:00, forever
--run-now       with --daemon: run one day immediately, then the schedule
--fast          every agent on the small model (llama3.2:3b)
--offline       zero LLM calls — heuristic Jev + stub agents (CI/debug)
--no-viz        skip all chart rendering
--no-learn      skip the midnight learning cycle
--dump FILE     append each day's verdict/state/learning to JSON
```

## Daemon mode (automatic midnight runs)

```bash
nohup python3 main.py --daemon --dump sim_log.json > daemon.out 2>&1 &
```

Behavior:

- Prints a timestamped banner when a new day starts and when each image is
  saved; between runs it prints `waiting for midnight (Xh until next cycle)`.
- Sleeps in 30 s slices — SIGTERM/SIGINT shut it down promptly and the
  checkpoint is always current.
- The `--dump` file doubles as the checkpoint: point the daemon at the same
  file on restart and it resumes the same world, agent memory included.
- If a day crashes, the error is logged and it retries next midnight —
  the checkpoint is never left half-written.
- After checkpointing it writes the day's ready-to-post summary file
  (see below).

## Daily post file (manual X/Twitter)

After each midnight cycle the sim writes `posts/dayN_tweet.txt`
(`simulation/dailypost.py`) — a ready-to-paste post for
@zahra_hnf16553 containing:

- day/date, Jev P(war 72h) · P(deal 7d) · P(Iran collapse), the Brent
  settle, the day's most influential agent's predicted event, and an
  explicit *"AI simulation — not a real-world forecast"* disclaimer —
  plus a reminder to attach `dayN_predictions.png`.

There is no API integration — open the file, paste the text into X,
attach the PNG, done. The file is regenerated fresh each midnight along
with all other artifacts.

## Configuration

Everything model-related lives in `config.py`, overridable by env:

| Env var | Default | Role |
|---|---|---|
| `SIM_JEV_MODEL` | `llama3.2:3b` | decision layer (should stay small/fast) |
| `SIM_AGENT_MODEL` | `qwen35-uncensored` | default character model |
| `SIM_FAST_MODEL` | `llama3.2:3b` | oil market, sentiment tracker, `--fast` |
| `OLLAMA_HOST` | `http://localhost:11434` | local Ollama endpoint |

Notes: thinking-style models (qwen3.5, deepseek-r1, gemma4) are called with
`think=false` — otherwise they can exhaust `num_predict` on reasoning and
return empty statements. A bigger `SIM_JEV_MODEL` gives more differentiated
probabilities at the cost of speed.

## Requirements

- Python 3.10+, a running local Ollama — that's it for the sim core
  (stdlib-only HTTP client).
- `matplotlib` + `pillow` for charts/GIFs (`requirements.txt`).

```bash
ollama pull llama3.2:3b
ollama pull qwen35-uncensored
```

## File map

```
main.py                  CLI entry (+ daemon mode)
config.py                models, temperatures, endpoints
ollama_client.py         stdlib-only /api/chat client (think=false handled)
jev/                     decision layer
  types.py               JevAnswer (choice|noul|score), TurnGate, RoundVerdict
  client.py              typed questions -> JSON -> validation -> heuristic fallback
agents/
  personas.py            the 8 in-character system prompts
  base.py                generation, output parsing, memory + learn()
simulation/
  state.py               SituationState, Sept-2026 seed, date advance, resume
  xfeed.py               seeded X/Twitter posts per round (agents must cite)
  world.py               action->state rules, fair-Brent model, drift
  director.py            the day loop, Jev gates, midnight learning, artifacts
  viz.py                 GIF animation + learning/prediction/history PNGs
  daemon.py              resident 00:00 scheduler with checkpointing
real_events/dayN.txt     optional real-world injection for the learning cycle
```

## Gallery

Round 1 — the day unfolds act by act; each frame is one agent's move:

![Round 1 animation](round1_animation.gif)

Round 2 — Hormuz partially closed; watch Brent climb past $150 while Jev
keeps denying escalation (black ✕ markers on the war panel):

![Round 2 animation](round2_animation.gif)

Midnight learning board — per-agent lessons, predictions for tomorrow,
and who actually moved the world state:

![Day 1 learning](day1_learning.png)

Focused predictions — tonight's calls vs Jev's reference lines:

![Day 3 predictions](day3_predictions.png)

Before vs after learning — how beliefs moved overnight:

![Day 3 before/after](day3_before_after.png)

Cumulative history — oil track, Jev probability track, influence totals:

![Simulation history](sim_history.png)

## Steer the simulation

- **Inject reality**: write `real_events/dayN.txt` before a midnight run —
  it's added to the ground truth every agent learns from.
- **Steer the feed**: add posts to `ROUND_POSTS[N]` in
  `simulation/xfeed.py` — agents cite them, the market reacts.
- **Tune the world**: `simulation/world.py` controls every action→state
  mapping and the oil model.
- **Tune Jev**: question text and the heuristic fallback live in
  `jev/client.py`.
- **Tune personas**: `agents/personas.py` — one system prompt each.

## Honest caveats

- Jev on a 3B model anchors scores (you'll see repeated 0.23s). Point
  `SIM_JEV_MODEL` at a larger model for sharper probabilities.
- `who_acts_next` occasionally fails JSON validation and falls back to the
  heuristic picker (visible as `[fallback]` in the transcript).
- The world model is keyword-driven — agents' *wording* moves the world,
  which is intentional but coarse. Richer effect parsing is the obvious
  next step.

---

*Everything runs on your machine. No API keys, no cloud calls — just
Ollama and Python.*