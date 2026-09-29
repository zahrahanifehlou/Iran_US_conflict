# Iran – US – Israel Conflict Simulation (Sept 2026)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLMs-000000?logo=ollama&logoColor=white)](https://ollama.com)
[![Charts](https://img.shields.io/badge/charts-matplotlib-11557c)](https://matplotlib.org)
[![Runs](https://img.shields.io/badge/runs-100%25%20local-success)](config.py)

A fully local multi-agent geopolitical simulation. Nineteen LLM agents in
three layers play state and non-state actors in a fictionalized
September-2026 Iran–US–Israel war, governed by **Jev**, a small typed
decision layer that controls who acts, who may escalate, and the headline
probabilities of war, deal, and collapse. A resident daemon advances the
simulation one day every 12 hours, learns overnight, renders charts, and
publishes the artifacts to GitHub.

The architecture is a deliberate System-2 / System-1 split:

- **Agents (large model)** stay in character: statements, strategy,
  private reasoning, nightly reflection. They never decide game mechanics.
- **Jev (small fast model)** never writes prose. It returns only typed
  answers: `choice` (who acts next), `noul` (yes/no gate), or `score`
  (probability 0–1).
- **Swarm (no model)** aggregates all agents' nightly forecasts into a
  second, independent consensus voice for comparison against Jev.

## Requirements

- Python 3.10+ and a running local [Ollama](https://ollama.com) instance —
  the sim core is stdlib-only.
- `matplotlib` + `pillow` for charts (`requirements.txt`).

```bash
ollama pull llama3.2:3b
ollama pull qwen35-uncensored
python3 main.py --rounds 1 --dump sim_log.json   # run one day
```

## Scenario seed (25 September 2026)

- ~7 months into the war. Khamenei Sr. was killed early on; **Mojtaba
  Khamenei** is Supreme Leader and the IRGC dominates the war cabinet.
- Trump framed a binary choice at the UNGA: a deal that lets Iran rebuild,
  or annihilation. Back-channel talks continue on the sidelines.
- Limited exchanges of fire continue. Brent ≈ $100, US midterms ~40 days
  out, Iran under blockade (~60% inflation, rial ≈ 1.65M/USD).

## The agents — all 19, in three layers

Each agent is a frozen persona (`agents/personas.py`) with its own goals,
fears, and memory. `qwen35-uncensored` plays the characters by default.

### Geopolitical — states that move armies and sign deals

| Agent | What drives it |
|---|---|
| **US** (Trump White House) | Look strong before midterms; keep gas cheap; a deal sold as total victory is ideal — but escalates if humiliated. |
| **Israel** (Netanyahu govt) | Permanently eliminate Iran's nuclear capacity; will act alone to kill a bad deal. |
| **Iran** (IRGC + Mojtaba) | Regime survival; keep the 60% stockpile as insurance; weaponize oil/Hormuz leverage; outwait US domestic pain. |
| **Russia** | High oil prices fund its war economy; arms sales to Tehran; wants the war long and expensive — for America. |
| **China** | Keep Hormuz open; buy discounted Iranian barrels; pose as mediator; study US war-prosecution for the Taiwan file. |
| **EU** | De-escalation above all — cannot absorb another energy shock; offers escrow and sanctions-relief architecture. |
| **Taiwan** | US carriers diverted to the Gulf thin its deterrence; trades semiconductor/intel cooperation for reassurance. |
| **Gulf** (Saudi-led GCC) | No Iranian bomb, but no war on Gulf soil; spare capacity released only for hard US security guarantees. |
| **Turkey** | NATO's southern flank hosting Incirlik while brokering corridors; de-escalates loudly, profits quietly. |

### Economic — markets that price the war in real time

Structured-output agents; at day settle their calls blend 50/50 with the
world model's fair value.

| Agent | Output |
|---|---|
| **Oil market** | `BRENT:` + `FORECAST:` — Hormuz premium, incidents, SPR. |
| **Gas / LNG** | `TTF:` + `FORECAST:` — Qatari LNG transits Hormuz; no SPR for gas. |
| **Shipping & insurance** | `INSURANCE:` + `FREIGHT:` — war-risk % of hull, VLCC rerouting. |
| **Financial markets** | `GOLD:` + `SPX_DIR:` — safe-haven flows, rate repricing. |
| **Central banks** | Fed/ECB composite — trapped between energy inflation and recession. |

### Society / information — the constraint surface

| Agent | What it is |
|---|---|
| **US public** | Midterm voters: cheap gas, no endless wars, no body bags. |
| **Iranian public** | Street + sentiment tracker: protests, war fatigue, rally-round-the-flag. |
| **Israeli public** | Reservist fatigue, displaced north, hostage families, brain drain. |
| **Media** | The information environment — chooses frames, not sides. |
| **Humanitarian** | UN OCHA/ICRC composite: casualties, displacement, access corridors. |

## How a day runs — acting and reacting

```
SituationState ──> Jev: who acts next?  ──loop──>  per chosen agent:
   ▲                 │                           Jev: escalation permitted?  (noul)
   └─ live wire      │                           Jev: needs human review?    (noul)
     (real headlines │                           agent speaks — cites a feed
      each morning)  │                            post via XREF, gives private
                     │                            REASONING + ACTION, then the
                     │                            world model applies effects
                     ▼
              Jev scores: P(war 72h) · P(deal 7d) · P(collapse)
              oil settle: market call vs Jev realism check
              MIDNIGHT: learning -> predictions -> swarm consensus
              render charts -> posts/dayN_tweet.txt -> checkpoint -> push
```

**Reactions.** Each act is a *reaction*, not a free-form turn: the agent
reads the feed posts addressed to it, picks one to respond to (`XREF:
@handle`), and declares a `STATEMENT` (public), `REASONING` (private), and
`ACTION` (what it actually does, optionally flagged `ESCALATION
REQUESTED`). The action log persists per day and is rendered as an
animated interaction network (`media/roundN_interactions.gif`): agents on
a ring colored by layer, an edge per citation, red edges for escalation
requests, unmapped handles routed to a central X-FEED hub.

**Jev's seven questions per round:**

| Question | Type | Used for |
|---|---|---|
| Who acts next? | `choice` | acting order (or `end_round`) |
| Escalation permitted? | `noul` | per-agent military gate |
| P(war 72h) / P(deal 7d) / P(collapse) | `score` | round verdict + history track |
| Oil reaction realistic? | `noul` | if NO, the fair-value model overrides the market call |
| Needs human review? | `noul` | flagged actions run under a review hold |

**Score calibration** (`jev/calibrate.py`): small models anchor on a
prior (~0.23), so headline scores are re-issued through a calibrator that
knows Jev's own track record:
`calibrated = 0.75·(raw − 0.5·bias) + 0.25·base_rate`, where *bias* is
mean(raw − realized) and *base_rate* the empirical event frequency.
Realized events come from the sim's day-over-day deltas. With fewer than
two scored days the raw value passes through.

**The world model** (`simulation/world.py`) maps wording to numbers:
"strike/missile" raises war intensity, "close/shut/mine" degrades Hormuz,
"ceasefire/framework" strengthens diplomacy, "sanction" raises economic
pressure, and great-power levers ("arms sale", "yuan settlement", "spare
capacity", "mediate") each have their own effects. Markets: Brent drifts
toward `82 + Hormuz_premium + 1.2·intensity + 2·incidents`; WTI, gold,
and war-risk insurance tick alongside. French pump prices
(`petrol = 1.62 + 0.006·Brent`, damped ~60% by tax) are the impact layer —
"rebate/price cap" language activates a visible, temporary rebate.
Per-act deltas are summed into an **influence** score per agent (ambient
drift excluded, so it measures agency, not luck).

## Learning — how agents get smarter overnight

**No weights are ever updated** — no fine-tuning, no gradients. All
learning is in-context: what changes is the text each agent is fed. Every
byte of it is auditable in `sim_log.json`. The midnight cycle:

1. **Ground truth assembled** — the day's state deltas, Jev's scores, and
   the real-world wire from `real_events/dayN.txt`.
2. **Matured claims graded first** — pending predictions whose horizon
   elapsed are judged against that blob: Jev returns a typed yes/no
   verdict online, a keyword-overlap heuristic offline. Undetermined
   claims expire after one day rather than being scored as wrong.
3. **Results injected as prompt text** — the actual training signal:
   `YOUR PREDICTIONS THAT JUST RESOLVED: [72h] 'X' -> WRONG (you gave
   85%)`. An agent that cries wolf reads its own failed calls every night
   and measurably cools off.
4. **Typed update returned** — `LEARNED / BELIEF / STANCE / PRED_24H…
   PRED_30D (with confidence) / SOURCE / P_WAR / P_DEAL / BRENT_DIR`.
5. **Carried into tomorrow** — `LEARNED` joins an 8-lesson rolling memory
   and `STANCE` is replaced; both are injected into the next *daytime*
   prompt, so lessons change actions, not just forecasts.
6. **Persisted** — memory, stance, pending claims, and stats are written
   to the dump; `--resume` and daemon restarts keep the ledger continuous.

## Predictions — falsifiable bets, not vibes

Each midnight every agent files **five dated claims** with confidence and
a declared information source:

| Horizon | What agents predict |
|---|---|
| 24h | major military escalation / de-escalation |
| 72h | new attacks, ceasefire, retaliation, diplomacy |
| 7d | conflict intensity, Hormuz/shipping disruption |
| 14d | oil direction, great-power policy responses |
| 30d | sanctions, negotiations, deployments, expansion |

**Metrics tracked** per agent, cumulative, rendered nightly to
`media/prediction_scoreboard.png`:

- Accuracy and mean Brier score `(conf − outcome)²`
- Calibration curve — confidence bins vs empirical frequency
- False positives / false negatives
- Accuracy **by horizon** (24h → 30d) and **by source** — each prediction
  declares whether `xfeed | wire | markets | memory | transcript` drove
  it, so you can see which signals actually pay off

## The swarm — a second forecasting voice

After the learning cycle every agent has already filed `P_WAR / P_DEAL /
BRENT_DIR`, so `simulation/swarm.py` costs no extra model calls. It runs a
UNU-style iterated convergence: votes weighted by the voter's track
record; each iteration pulls positions toward the skill-weighted mean with
`pull · (1 − skill)`, so proven forecasters are sticky and unproven ones
get dragged. Residual dispersion is kept deliberately — it measures honest
disagreement and feeds `conviction`. The result prints a `SWARM
CONSENSUS` block nightly, lands in the dump (including `jev_gap`, the
swarm-vs-Jev distance — itself a signal), and adds a line to the daily
post. `SIM_SWARM=0` disables it.

## Live data sources

No API keys, no scraping behind paywalls — plain unauthenticated GETs in
`simulation/realworld.py`, 12 s timeout, all **fail soft**.

| What | Source | Refreshed |
|---|---|---|
| Brent `BZ=F` / WTI `CL=F` / Gold `GC=F` | [Yahoo Finance chart endpoint](https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=5d) | midnight, per day |
| French pump prices | [fuel-prices.eu/France](https://www.fuel-prices.eu/France/) | midnight, per day |
| Conflict headlines | [Google News RSS](https://news.google.com/rss/search?q=Iran%20Israel%20war%20OR%20Strait%20of%20Hormuz%20OR%20Brent%20crude%20when:1d&hl=en-US&gl=US&ceid=US:en) (`when:1d`) | twice — 5 at day open, 8 at midnight |
| Model inference | local Ollama `http://localhost:11434` | every call |

Information flow: the morning headlines enter every agent prompt as a
`LIVE WIRE` block; the midnight fetch persists to `real_events/dayN.txt`
and is appended to ground truth. **A hand-written `real_events/dayN.txt`
takes precedence** — drop your own file there to inject any wire.
`--offline` skips all HTTP and LLM calls (heuristic Jev, stub agents).

Two things are not live, by design: the scenario itself (September 2026 is
fictional — real data only grades forecasts, never drives the plot) and,
by default, the social feed.

## The social feed — real posts, no paid API

`simulation/xfeed.py` is a pluggable provider layer:

```
XFeed
├── SyntheticXFeed     hand-written posts — deterministic; tests + offline
├── RealPublicXFeed    real X posts from free public endpoints
└── BlueskyPublicFeed  real posts via Bluesky's public unauthenticated API
```

**The honest limitation:** there is no free public X *search* API, and
every public Nitter instance is dead. What exists unauthenticated is
`syndication.twitter.com` — the backend behind X's own embed widgets —
which `RealPublicXFeed` queries once per watched account. It is heavily
rate-limited (often 429) and **never retried around**. If zero posts
arrive, the feed raises `Real X feed unavailable…` and agents are told
explicitly there are no posts — nothing is ever fabricated silently.
`provider: bluesky` is the working free alternative; posts arrive labelled
`source: bluesky`, never as X. `provider: auto` tries X first, then
Bluesky, recording `fallback_from: real-x` when it substitutes.

Every post normalizes to `{post_id, author, text, created_at, url,
retrieved_at, source}`, is deduplicated by `post_id`, and query-filtered
before reaching agents. Successful collections cache to
`cache/xfeed/<provider>_<queryhash>.json` (gitignored, default TTL 12 h) —
re-runs serve from disk; an expired cache used after a failed fetch is
flagged `stale-cache`. Provenance is visible in the console `[FEED]` line,
the dump's `xfeed` block, and the agent prompt header, which states
plainly whether posts are real X, real Bluesky, or fictional.

```bash
SIM_FEED_PROVIDER=auto python3 main.py --daemon --dump sim_log.json
python3 main.py --feed bluesky            # per-run override
```

Tests (fully mocked HTTP): `python3 -m unittest discover -s tests` —
39 tests covering parsing, normalization, dedup, caching, provenance,
filtering, and unavailable-source handling, plus swarm, scheduler, and
renderer tests.

## Generated artifacts — every day

| File | Contents |
|---|---|
| `media/roundN_animation.gif` | 4-panel build, one frame per act: Brent path, war intensity (✕ = Jev denied escalation, ★ = review flag), Iran street/regime, US domestic, Jev's closing scores. |
| `media/roundN_interactions.gif` | Animated agent-interaction network: who cited whom, reasoning captions, red edges for escalation requests. |
| `media/roundN_network.png` / `roundN_summary.png` | Static versions of the interaction map and the final frame. |
| `media/dayN_learning.png` | Midnight board: lessons, predictions, Brent calls, scorecards, influence ranking. |
| `media/dayN_predictions.png` | Per-agent P(war)/P(deal) bars vs Jev's reference lines. |
| `media/dayN_before_after.png` | Dumbbell chart: last night's call vs tonight's post-learning revision. |
| `media/sim_history.png` | Cumulative Brent & gas track (Hormuz-shaded), Jev probability track, cumulative influence. |
| `media/prediction_scoreboard.png` | Accuracy + Brier per agent, calibration curve, accuracy by horizon. |
| `media/fuel_track.png` | Pass-through chain: Hormuz insurance + Brent upstream, French pump downstream, rebate windows. |
| `posts/dayN_tweet.txt` | Ready-to-paste post: day/date, Jev scores, swarm line, Brent, key call, disclaimer. |
| `real_events/dayN.txt` | The day's real-world wire, verbatim. |
| `sim_log.json` | Checkpoint: world state, memories, predictions, swarm, feed provenance. |

## Usage

```
python3 main.py [options]

--rounds N      simulate N days in one process
--resume FILE   continue from a --dump file (world + memories + history)
--daemon        stay resident; run one day every 12h (00:00 / 12:00)
--run-now       with --daemon: run one day immediately, then the schedule
--fast          every agent on the small model
--offline       zero LLM calls — heuristic Jev + stub agents
--no-viz        skip chart rendering        --no-learn  skip the learning cycle
--dump FILE     append each day's verdict/state/learning to JSON
--push          publish artifacts after a one-off run
--no-push       disable publishing in daemon mode
--feed P        social feed: synthetic | real | bluesky | auto
```

### Daemon mode

```bash
SIM_FEED_PROVIDER=auto nohup python3 main.py --daemon --dump sim_log.json > daemon.out 2>&1 &
```

Runs one simulated day at each **12-hour clock mark (00:00 and 12:00)** —
marks are absolute, so restarts never drift the schedule
(`SIM_CYCLE_HOURS` changes the cadence). Sleeps in 30 s slices and fires
on resume if the machine slept through a mark. A single-instance `flock`
guard refuses a second daemon. A crashed day logs the error and retries
next cycle; the checkpoint is never half-written.

### Auto-publishing

In daemon mode each completed day is committed and pushed
(`simulation/autopush.py`) once charts, post, and checkpoint are on disk.
Rules: **only artifacts are staged** (`media/`, `posts/`, `real_events/`,
the dump — source edits are never swept in); **never force-pushes** — a
diverged remote logs the rejection and keeps the commit local; no empty
commits; 120 s timeout with `BatchMode=yes` so it can never hang on a
credential prompt. History grows ~2.5 MB/run of binary artifacts — switch
`media/` to `git lfs track` if that becomes a problem.

## Configuration

All in `config.py`, env-overridable:

| Env var | Default | Role |
|---|---|---|
| `SIM_JEV_MODEL` | `llama3.2:3b` | decision layer (keep small/fast) |
| `SIM_AGENT_MODEL` | `qwen35-uncensored` | default character model |
| `SIM_FAST_MODEL` | `llama3.2:3b` | market/tracker agents, `--fast` |
| `SIM_CYCLE_HOURS` | `12` | daemon cadence |
| `SIM_AUTOPUSH` | `1` | `0` disables auto commit+push |
| `SIM_FEED_PROVIDER` | `synthetic` | `real` · `bluesky` · `auto` |
| `SIM_FEED_QUERY` | `Iran OR Israel OR …` | feed search terms |
| `SIM_FEED_CACHE` / `SIM_FEED_TTL_H` | `1` / `12` | feed caching |
| `SIM_SWARM` (+`_PULL`,`_ITERS`,`_EPS`) | `1` | swarm consensus tuning |

Thinking-style models are called with `think=false` so they don't exhaust
`num_predict` on hidden reasoning.

## File map

```
main.py              CLI entry + daemon mode
config.py            models, feed and swarm configuration
ollama_client.py     stdlib-only /api/chat client
jev/                 types.py · client.py · calibrate.py
agents/              personas.py (19 system prompts) · base.py (act/learn)
simulation/
  state.py           SituationState, scenario seed, resume
  director.py        day loop, Jev gates, learning, artifacts
  world.py           action->state rules, fair-value market model
  xfeed.py           feed providers: synthetic / real public X / Bluesky
  realworld.py       market quotes + headlines fetch (no keys)
  predictions.py     prediction ledger: horizons, judging, Brier
  swarm.py           skill-weighted nightly consensus
  viz.py             all charts and GIFs -> media/
  daemon.py          12-hour scheduler, checkpoint, single-instance lock
  dailypost.py       posts/dayN_tweet.txt
  autopush.py        commits + pushes the day's artifacts
```

## Steering the simulation

- **Inject reality**: write `real_events/dayN.txt` before a run — it
  becomes ground truth for learning.
- **Steer the feed**: add posts to `ROUND_POSTS[N]` in `xfeed.py`, or run
  `--feed auto` for real posts.
- **Tune the world**: `world.py` holds every action→state mapping.
- **Tune Jev / personas**: `jev/client.py`, `agents/personas.py`.

## Honest caveats

- Jev on a 3B model anchors scores (repeated 0.23s); a larger
  `SIM_JEV_MODEL` sharpens probabilities.
- `who_acts_next` occasionally fails JSON validation and falls back to a
  heuristic picker (visible as `[fallback]`).
- The world model is keyword-driven — agents' *wording* moves the world.
  Intentional, but coarse.
- Free public X access is unreliable by nature; expect `auto` to serve
  labelled Bluesky posts most days.

## Gallery

![Round 1 animation](media/round1_animation.gif)
![Day 4 predictions](media/day4_predictions.png)
![Prediction scoreboard](media/prediction_scoreboard.png)
![Simulation history](media/sim_history.png)

---

*Everything runs on your machine. No API keys, no cloud calls — just
Ollama and Python.*
