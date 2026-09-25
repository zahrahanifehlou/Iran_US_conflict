"""The Director — orchestrates each round.

Flow per round:
  1. Print Situation State.
  2. Loop: Jev picks who acts next (or 'end_round'); for each chosen agent,
     Jev answers escalation-permitted and human-review gate questions; the
     agent then speaks, citing X posts.
  3. World-update rules + market agent's Brent call produce the new price;
     Jev validates the oil reaction.
  4. Jev emits 72h / 7d / 7-14d probability scores.
"""

from __future__ import annotations

import json
import sys

from agents import Agent, BY_ID, ALL_IDS
from jev import JevClient, RoundVerdict, TurnGate
from .state import SituationState, initial_state
from .xfeed import feed_for
from . import world

BAR = "=" * 72
SUB = "-" * 72


def _p(s=""):
    print(s, flush=True)


class Director:
    def __init__(self, state: SituationState | None = None,
                 fast: bool = False, offline: bool = False,
                 max_acts_per_round: int = 8):
        self.state = state or initial_state()
        self.jev = JevClient(offline=offline)
        self.agents = {aid: Agent(BY_ID[aid], fast=fast) for aid in ALL_IDS}
        self.max_acts = max_acts_per_round
        self.offline = offline

    # ------------------------------------------------------------ printing
    def _jev_line(self, label, ans):
        _p(f"  [JEV] {label:<46} -> {ans.fmt()}")

    # ------------------------------------------------------------ one round
    def run_round(self) -> dict:
        st = self.state
        verdict = RoundVerdict()
        _p(BAR)
        _p(st.human_summary())
        _p(BAR)

        state_dict = st.to_dict()
        transcript: list[str] = []
        acted: list[str] = []
        actions = []

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
                _p(f"  !! HUMAN REVIEW FLAGGED — action proceeds under "
                   f"review hold")

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
            state_dict = st.to_dict()

        # ------------------------------------------------ scores this round
        _p(f"\n{SUB}\nJEV ROUND SCORES")
        verdict.p_war_72h = self.jev.p_war_72h(state_dict)
        self._jev_line("P(full-scale war escalation, 72h)", verdict.p_war_72h)
        verdict.p_deal_7d = self.jev.p_deal_7d(state_dict)
        self._jev_line("P(temporary deal / ceasefire, 7d)", verdict.p_deal_7d)
        verdict.p_collapse = self.jev.p_collapse(state_dict)
        self._jev_line("P(Iranian econ collapse accelerates)", verdict.p_collapse)

        # ------------------------------------------------ world update
        notes = world.apply_actions(st, actions)
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

        # ------------------------------------------------ 7-14d forecast
        _p(f"\n{SUB}\nJEV FORECAST — next 7-14 days")
        verdict.forecast = self.jev.forecast_7_14d(st.to_dict())
        for k, a in verdict.forecast.items():
            self._jev_line(k.replace("_", " "), a)

        # ------------------------------------------------ updated state
        _p(f"\n{SUB}\nUPDATED SITUATION")
        for n in notes:
            _p(f"  * {n}")
        _p(f"  * Brent ${prev:.1f} -> ${st.brent:.1f} "
           f"(forecast ${st.brent_forecast:.1f}) | "
           f"US gas ${st.us_gas_price:.2f}/gal")
        _p(f"  * war intensity {st.war_intensity:.1f}/10 | Hormuz: "
           f"{st.hormuz_status.replace('_', ' ')} | "
           f"regime cohesion {st.regime_stability:.0%} | "
           f"protests {st.iran_protest_level:.1f}/10")
        _p(BAR)

        st.round_no += 1
        return {"verdict": verdict.to_dict(),
                "state": st.to_dict(),
                "transcript": transcript}

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
        stmt = a.statement if a.statement != a.raw else a.raw
        _p(f"  STATEMENT: {stmt}")
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


def main(rounds: int, fast: bool, offline: bool, dump: str | None):
    d = Director(fast=fast, offline=offline)
    log = []
    for _ in range(rounds):
        log.append(d.run_round())
    if dump:
        with open(dump, "w") as f:
            json.dump(log, f, indent=2)
        _p(f"\nTranscript + Jev verdicts written to {dump}")
