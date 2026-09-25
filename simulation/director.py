"""The Director — orchestrates each round.

Flow per round:
  1. Print Situation State.
  2. Loop: Jev picks who acts next (or 'end_round'); for each chosen agent,
     Jev answers escalation-permitted and human-review gate questions; the
     agent then speaks, citing X posts. After every act the world state is
     nudged and a snapshot is taken — the snapshots drive the animation.
  3. Structural drift + the market agent's Brent call set the new price;
     Jev validates the oil reaction (fair-value override if unrealistic).
  4. Jev emits 72h / 7d / 7-14d probability scores.
  5. Animated GIF + summary PNG are written for the round.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

from agents import Agent, BY_ID, ALL_IDS
from jev import JevClient, RoundVerdict, TurnGate
from .state import (SituationState, initial_state, state_from_full,
                    _advance_date_range)
from .xfeed import feed_for
from . import world

BAR = "=" * 72
SUB = "-" * 72

SHORT = {
    "trump": "TRUMP", "netanyahu": "NETANYAHU", "iran_hardliners": "IRGC",
    "iranian_people": "IR-PEOPLE", "eu": "EU", "oil_market": "OIL",
    "us_public": "US-PUBLIC", "iran_sentiment": "IR-STREET",
    "start": "START", "end": "END",
}


def _p(s=""):
    print(s, flush=True)


def _val(ans):
    return None if ans is None else round(float(ans.value), 3)


def _fmt(ans):
    return "n/a" if ans is None else f"{ans.value:.2f}"


class Director:
    def __init__(self, state: SituationState | None = None,
                 fast: bool = False, offline: bool = False,
                 viz: bool = True, learn: bool = True,
                 max_acts_per_round: int = 8):
        self.state = state or initial_state()
        self.jev = JevClient(offline=offline)
        self.agents = {aid: Agent(BY_ID[aid], fast=fast) for aid in ALL_IDS}
        self.max_acts = max_acts_per_round
        self.offline = offline
        self.viz = viz
        self.learn = learn
        self.snapshots: list[dict] = []
        self.history: list[dict] = []       # one entry per finished day

    # ------------------------------------------------------- influence
    _TRACKED = ("war_intensity", "brent", "iran_protest_level",
                "iran_econ_pressure", "regime_stability", "us_gas_price")

    def _influence(self, before: dict) -> float:
        """How much this act moved the tracked world metrics."""
        st = self.state
        after = {
            "war_intensity": st.war_intensity, "brent": st.brent / 10,
            "iran_protest_level": st.iran_protest_level,
            "iran_econ_pressure": st.iran_econ_pressure,
            "regime_stability": st.regime_stability * 10,
            "us_gas_price": st.us_gas_price * 2,
        }
        return round(sum(abs(after[k] - before[k]) for k in self._TRACKED), 2)

    def _tracked_now(self) -> dict:
        st = self.state
        return {
            "war_intensity": st.war_intensity, "brent": st.brent / 10,
            "iran_protest_level": st.iran_protest_level,
            "iran_econ_pressure": st.iran_econ_pressure,
            "regime_stability": st.regime_stability * 10,
            "us_gas_price": st.us_gas_price * 2,
        }

    # ------------------------------------------------------------ helpers
    def _jev_line(self, label, ans):
        _p(f"  [JEV] {label:<46} -> {ans.fmt()}")

    def _snapshot(self, label: str, event: str = "", esc_denied: bool = False,
                  review: bool = False):
        st = self.state
        self.snapshots.append({
            "step": len(self.snapshots),
            "label": label,
            "brent": round(st.brent, 2),
            "forecast": round(st.brent_forecast, 2),
            "war": round(st.war_intensity, 2),
            "gas": round(st.us_gas_price, 2),
            "war_support": round(st.us_war_support, 3),
            "protests": round(st.iran_protest_level, 2),
            "cohesion": round(st.regime_stability, 3),
            "econ_pressure": round(st.iran_econ_pressure, 2),
            "hormuz": st.hormuz_status,
            "event": event,
            "esc_denied": esc_denied,
            "review": review,
        })

    # ------------------------------------------------------------ one round
    def run_round(self) -> dict:
        st = self.state
        verdict = RoundVerdict()
        self.snapshots = []
        _p(BAR)
        _p(st.human_summary())
        _p(BAR)

        self._snapshot("start", "round opens")
        state_dict = st.to_dict()
        transcript: list[str] = []
        acted: list[str] = []
        actions = []
        day_notes: list[str] = []
        influence_map: dict[str, float] = {}

        _p("\n[JEV] Deciding acting order...")
        for _ in range(self.max_acts):
            nxt = self.jev.who_acts_next(state_dict,
                                         [a for a in ALL_IDS if a not in acted])
            self._jev_line("who acts next?", nxt)
            if nxt.value == "end_round" or nxt.value not in ALL_IDS:
                break
            aid = nxt.value
            verdict.acting_order.append(aid)
            acted.append(aid)

            esc = self.jev.allow_escalation(state_dict, aid)
            self._jev_line(f"escalation permitted for {aid}?", esc)
            rev = self.jev.needs_human_review(state_dict, aid)
            self._jev_line(f"needs human review ({aid})?", rev)
            verdict.gates[aid] = TurnGate(aid, esc, rev)

            if rev.value:
                _p("  !! HUMAN REVIEW FLAGGED — action proceeds under "
                   "review hold")

            agent = self.agents[aid]
            if self.offline:
                action = self._offline_act(agent, st)
            else:
                _p(f"  ... {agent.p.name} speaking ({agent.model})")
                try:
                    action = agent.act(st, feed_for(st.round_no, aid),
                                       bool(esc.value), transcript)
                except Exception as exc:
                    _p(f"  !! model call failed for {aid}: {exc} — offline line")
                    action = self._offline_act(agent, st)
            actions.append(action)
            self._print_action(action)
            transcript.append(
                f"{action.name}: {action.statement[:180]} | ACTION: "
                f"{action.proposed_action[:120]}")

            # ---- intra-round world update -> snapshot for the animation
            before = self._tracked_now()
            notes = world.apply_single_action(st, action)
            influence = self._influence(before)   # action's own deltas only
            world.tick_brent(st)                  # ambient market move (unattributed)
            day_notes.extend(notes)
            influence_map[aid] = influence_map.get(aid, 0.0) + influence
            ev = action.proposed_action or action.statement
            flag = " [esc denied]" if action.escalation_requested and not esc.value else ""
            self._snapshot(SHORT.get(aid, aid),
                           f"{SHORT.get(aid, aid)}: {ev[:140]}{flag}",
                           esc_denied=action.escalation_requested and not esc.value,
                           review=bool(rev.value))
            self.snapshots[-1]["influence"] = influence
            state_dict = st.to_dict()

        # ------------------------------------------------ scores this round
        _p(f"\n{SUB}\nJEV ROUND SCORES")
        verdict.p_war_72h = self.jev.p_war_72h(state_dict)
        self._jev_line("P(full-scale war escalation, 72h)", verdict.p_war_72h)
        verdict.p_deal_7d = self.jev.p_deal_7d(state_dict)
        self._jev_line("P(temporary deal / ceasefire, 7d)", verdict.p_deal_7d)
        verdict.p_collapse = self.jev.p_collapse(state_dict)
        self._jev_line("P(Iranian econ collapse accelerates)", verdict.p_collapse)

        # ------------------------------------------------ world settlement
        world.end_of_round_drift(st)
        oil = next((a for a in actions if a.agent_id == "oil_market"), None)
        brent_call = oil.fields.get("brent") if oil else None
        fc_call = oil.fields.get("forecast") if oil else None
        prev = st.brent
        world.apply_market(st, brent_call, fc_call, realistic=True)
        verdict.oil_realistic = self.jev.oil_realistic(state_dict, st.brent, prev)
        self._jev_line("is the oil price reaction realistic?",
                       verdict.oil_realistic)
        if not verdict.oil_realistic.value:
            _p("  [JEV] overriding market call with fair-value model")
            st.brent = world.fair_brent(st)
            st.brent_forecast = world.fair_brent(st) + 4
        self._snapshot("end", "round closes — Jev scores locked",
                       review=False)

        # ------------------------------------------------ 7-14d forecast
        _p(f"\n{SUB}\nJEV FORECAST — next 7-14 days")
        verdict.forecast = self.jev.forecast_7_14d(st.to_dict())
        for k, a in verdict.forecast.items():
            self._jev_line(k.replace("_", " "), a)

        # ------------------------------------------------ updated state
        _p(f"\n{SUB}\nUPDATED SITUATION")
        _p(f"  * Brent ${prev:.1f} -> ${st.brent:.1f} "
           f"(forecast ${st.brent_forecast:.1f}) | "
           f"US gas ${st.us_gas_price:.2f}/gal")
        _p(f"  * war intensity {st.war_intensity:.1f}/10 | Hormuz: "
           f"{st.hormuz_status.replace('_', ' ')} | "
           f"regime cohesion {st.regime_stability:.0%} | "
           f"protests {st.iran_protest_level:.1f}/10")
        _p(BAR)

        played_dates = st.date_range

        # ------------------------------------------------ midnight cycle
        learning = {}
        if self.learn:
            learning = self._midnight(played_dates, day_notes,
                                      verdict, influence_map)

        st.round_no += 1
        _advance_date_range(st)
        log = {"verdict": verdict.to_dict(),
               "date_range": played_dates,
               "state": st.to_dict(),
               "state_full": asdict(st),
               "snapshots": self.snapshots,
               "transcript": transcript,
               "influence": influence_map,
               "learning": learning}

        self.history.append({
            "day": st.round_no - 1,
            "date": played_dates,
            "brent": round(st.brent, 1),
            "gas": round(st.us_gas_price, 2),
            "war": round(st.war_intensity, 1),
            "hormuz": st.hormuz_status,
            "p_war_72h": _val(verdict.p_war_72h),
            "p_deal_7d": _val(verdict.p_deal_7d),
            "p_collapse": _val(verdict.p_collapse),
            "influence": influence_map,
        })

        if self.viz:
            self._render(log, st.round_no - 1)
            self._render_learning(log, st.round_no - 1)
            self._render_predictions(log, st.round_no - 1)
            self._render_history()
        try:
            from . import dailypost
            _p(f"Daily post: {dailypost.save_daily_post(log, st.round_no - 1)}")
        except Exception as exc:
            _p(f"!! daily post save failed: {exc}")
        return log

    def _render_predictions(self, log: dict, round_no: int):
        try:
            from . import viz
            a, b = viz.render_predictions(log, round_no)
            _p(f"Predictions: {a}\nBefore/After: {b}")
        except Exception as exc:
            _p(f"!! prediction charts failed: {exc}")

    # -------------------------------------------------- midnight learning
    def _midnight(self, day_label: str, day_notes: list[str],
                  verdict: RoundVerdict,
                  influence_map: dict) -> dict:
        st = self.state
        _p(f"\n{BAR}\nMIDNIGHT — LEARNING CYCLE  ({day_label} results are in)")
        _p(BAR)

        # what actually happened today (ground truth for every agent)
        truth_lines = ["OBSERVED OUTCOMES:"]
        truth_lines += [f"  - {n}" for n in day_notes] or ["  - quiet day"]
        truth_lines.append(
            f"  - Brent settled ${st.brent:.1f} | war intensity "
            f"{st.war_intensity:.1f}/10 | Hormuz {st.hormuz_status}")
        truth_lines.append(
            f"  - Iran: protests {st.iran_protest_level:.1f}/10, cohesion "
            f"{st.regime_stability:.0%} | US gas ${st.us_gas_price:.2f}")
        truth_lines.append(
            f"  - Jev: war72h {_fmt(verdict.p_war_72h)} | "
            f"deal7d {_fmt(verdict.p_deal_7d)} | "
            f"collapse {_fmt(verdict.p_collapse)}")
        # try to fetch the real-world wire first (Brent + headlines); if it
        # fails or a hand-written file exists, that file is used instead
        ev_file = f"real_events/day{st.round_no}.txt"
        if not os.path.exists(ev_file):
            try:
                from . import realworld
                if realworld.fetch_day(st.round_no):
                    _p(f"  [DIRECTOR] fetched real-world wire -> {ev_file}")
            except Exception as exc:
                _p(f"  [DIRECTOR] real-world fetch failed ({exc}) — "
                   f"continuing on simulated ground truth")
        if os.path.exists(ev_file):
            with open(ev_file) as f:
                injected = f.read().strip()
            truth_lines.append(f"REAL-WORLD WIRE ({ev_file}):\n{injected}")
            _p(f"  [DIRECTOR] injected real events from {ev_file}")
        ground_truth = "\n".join(truth_lines)

        learning = {}
        for aid in ALL_IDS:
            agent = self.agents[aid]
            if self.offline:
                agent.memory.append("(offline) no learning")
                learning[aid] = {"learned": "offline", "prediction": "—"}
                continue
            prev_pred = dict(agent.last_prediction)
            prev_stance = agent.stance
            try:
                upd = agent.learn(day_label, ground_truth, st)
            except Exception as exc:
                _p(f"  !! learn failed for {aid}: {exc}")
                continue
            sc = upd.fields.get("scorecard", {})
            learning[aid] = {
                "name": agent.p.name,
                "prev_prediction": prev_pred,
                "prev_stance": prev_stance,
                "learned": upd.fields.get("learned", ""),
                "belief": upd.fields.get("belief", ""),
                "stance": upd.fields.get("stance", ""),
                "prediction": upd.fields.get("prediction", ""),
                "p_war": upd.fields.get("p_war"),
                "p_deal": upd.fields.get("p_deal"),
                "brent_dir": upd.fields.get("brent_dir", ""),
                "scorecard": sc,
            }
            _p(f"\n  >> {agent.p.name} — learning update")
            _p(f"     LEARNED:    {upd.fields.get('learned', '—')}")
            _p(f"     BELIEF:     {upd.fields.get('belief', '—')}")
            _p(f"     STANCE:     {upd.fields.get('stance', '—')}")
            _p(f"     PREDICTS:   {upd.fields.get('prediction', '—')}")
            _p(f"     P_war {upd.fields.get('p_war','?')}/10 | "
               f"P_deal {upd.fields.get('p_deal','?')}/10 | "
               f"brent {upd.fields.get('brent_dir','?')} | "
               f"score {sc.get('hits',0)}W-{sc.get('misses',0)}L")
        return learning

    def _render(self, log: dict, round_no: int):
        try:
            from . import viz
            gif, png = viz.render_round(log, round_no)
            _p(f"\nAnimation: {gif}\nSummary:   {png}")
        except Exception as exc:
            _p(f"\n!! visualization failed: {exc}")

    def _render_learning(self, log: dict, round_no: int):
        try:
            from . import viz
            png = viz.render_learning(log, round_no)
            _p(f"Learning:  {png}")
        except Exception as exc:
            _p(f"!! learning chart failed: {exc}")

    def _render_history(self):
        try:
            from . import viz
            png = viz.render_history(self.history)
            _p(f"History:   {png}")
        except Exception as exc:
            _p(f"!! history chart failed: {exc}")

    def _print_action(self, a):
        _p(f"\n{SUB}\n>> {a.name}  [{a.model}]")
        if a.xref:
            _p(f"  reacts to {a.xref}")
        for key in ("mood", "protest_level", "war_fatigue",
                    "nationalism_rally", "black_market", "signal", "logic"):
            if key in a.fields:
                _p(f"  {key.upper()}: {a.fields[key]}")
        if "brent" in a.fields:
            _p(f"  BRENT: {a.fields['brent']}  FORECAST: "
               f"{a.fields.get('forecast', '?')}")
        if a.statement != a.raw:
            _p(f"  STATEMENT: {a.statement}")
        if a.proposed_action:
            esc = " [ESCALATION REQUESTED]" if a.escalation_requested else ""
            _p(f"  ACTION: {a.proposed_action}{esc}")

    @staticmethod
    def _offline_act(agent, st):
        from agents.base import AgentAction
        return AgentAction(
            agent.p.agent_id, agent.p.name,
            statement="(offline mode — LLM call skipped)",
            proposed_action="hold position", model="offline")


def _load_resume(path: str):
    """Return (state, history, memories) recovered from a --dump file."""
    try:
        with open(path) as f:
            logs = json.load(f)
        full = logs[-1].get("state_full")
        if not full:
            _p(f"!! {path} has no state_full (pre-viz dump?) — starting fresh")
            return None, [], {}
        history = []
        memories: dict[str, dict] = {}
        for entry in logs:
            if entry.get("influence") or entry.get("verdict"):
                v = entry.get("verdict", {})
                history.append({
                    "day": entry.get("state_full", {}).get("round_no", 1) - 1,
                    "date": entry.get("date_range", ""),
                    "brent": entry.get("state_full", {}).get("brent", 0),
                    "gas": entry.get("state_full", {}).get("us_gas_price", 0),
                    "war": entry.get("state_full", {}).get("war_intensity", 0),
                    "hormuz": entry.get("state_full", {}).get("hormuz_status", ""),
                    "p_war_72h": (v.get("p_war_72h") or {}).get("value"),
                    "p_deal_7d": (v.get("p_deal_7d") or {}).get("value"),
                    "p_collapse": (v.get("p_collapse") or {}).get("value"),
                    "influence": entry.get("influence", {}),
                })
            for aid, lrn in (entry.get("learning") or {}).items():
                m = memories.setdefault(aid, {"memory": [], "stance": "",
                                              "last_prediction": {}})
                if lrn.get("learned"):
                    m["memory"].append(lrn["learned"])
                m["stance"] = lrn.get("stance", m["stance"])
                m["last_prediction"] = {
                    "prediction": lrn.get("prediction", ""),
                    "p_war": lrn.get("p_war"),
                    "p_deal": lrn.get("p_deal"),
                    "brent_dir": lrn.get("brent_dir", ""),
                }
        return state_from_full(full), history, memories
    except Exception as exc:
        _p(f"!! could not resume from {path}: {exc} — starting fresh")
        return None, [], {}


def main(rounds: int, fast: bool, offline: bool, dump: str | None,
         resume: str | None = None, viz: bool = True, learn: bool = True):
    state, history, memories = (None, [], {})
    if resume:
        state, history, memories = _load_resume(resume)
    d = Director(state=state, fast=fast, offline=offline, viz=viz, learn=learn)
    d.history = history
    for aid, m in memories.items():
        if aid in d.agents:
            d.agents[aid].memory = m["memory"][-8:]
            d.agents[aid].stance = m["stance"]
            d.agents[aid].last_prediction = m["last_prediction"]
    log = []
    for _ in range(rounds):
        log.append(d.run_round())
    if dump:
        with open(dump, "w") as f:
            json.dump(log, f, indent=2)
        _p(f"\nTranscript + Jev verdicts written to {dump}")
