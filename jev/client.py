"""Jev — the fast typed decision layer.

Jev is asked narrow questions about the current SituationState and must reply
with a single JSON object, e.g.:

    {"value": "iran_hardliners", "confidence": 0.71}
    {"value": true,              "confidence": 0.64}
    {"value": 0.38,              "confidence": 0.55}

No prose, ever. If the model returns malformed output after retries, a
deterministic heuristic fallback answers instead and the answer is flagged
with source="heuristic-fallback" so it is visible in the transcript.
"""

from __future__ import annotations

import json
import re

import config
import ollama_client
from .types import JevAnswer, CHOICE, NOUL, SCORE


SYSTEM = (
    "You are JEV, a fast decision module inside a geopolitical simulation. "
    "You never write sentences. You receive a compact world state and one "
    "question, and you answer with ONE JSON object of the form "
    '{"value": <answer>, "confidence": <0..1>}. '
    "Base answers on incentives, power, and constraints — not sentiment. "
    "Output JSON only."
)

_KIND_HINT = {
    CHOICE: '"value" must be exactly one of the listed OPTIONS (a string).',
    NOUL: '"value" must be true or false.',
    SCORE: '"value" must be a number between 0.0 and 1.0 (a probability).',
}


class JevClient:
    def __init__(self, model: str | None = None, offline: bool = False):
        self.model = model or config.JEV_MODEL
        self.offline = offline          # force heuristic mode (no LLM calls)

    # ------------------------------------------------------------------ core
    def _ask(self, kind: str, question: str, state: dict,
             options: list[str] | None = None) -> JevAnswer:
        if not self.offline:
            for _ in range(config.JEV_RETRIES + 1):
                try:
                    ans = self._ask_model(kind, question, state, options)
                    if ans is not None:
                        return ans
                except ollama_client.OllamaError:
                    break
        return self._heuristic(kind, question, state, options)

    def _ask_model(self, kind: str, question: str, state: dict,
                   options: list[str] | None) -> JevAnswer | None:
        user = f"STATE: {json.dumps(state, separators=(',', ':'))}\n"
        if options:
            user += f"OPTIONS: {json.dumps(options)}\n"
        user += f"QUESTION: {question}\n{_KIND_HINT[kind]}\nJSON:"

        raw = ollama_client.chat(
            self.model,
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            temperature=config.JEV_TEMPERATURE,
            num_predict=config.JEV_NUM_PREDICT,
            json_mode=True,
        )
        return self._parse(kind, raw, question, options)

    @staticmethod
    def _parse(kind: str, raw: str, question: str,
               options: list[str] | None) -> JevAnswer | None:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        value, conf = obj.get("value"), obj.get("confidence", 0.5)
        try:
            conf = min(1.0, max(0.0, float(conf)))
        except (TypeError, ValueError):
            conf = 0.5

        if kind == SCORE:
            try:
                value = min(1.0, max(0.0, float(value)))
            except (TypeError, ValueError):
                return None
        elif kind == NOUL:
            if isinstance(value, str):
                value = value.strip().lower() in ("yes", "true", "1")
            if not isinstance(value, bool):
                return None
        elif kind == CHOICE:
            if not options or value not in options:
                # tolerate case/spacing drift
                match = next((o for o in (options or [])
                              if o.lower() == str(value).lower()), None)
                if match is None:
                    return None
                value = match
        return JevAnswer(question, kind, value, conf, "jev")

    # ---------------------------------------------------------- heuristics
    def _heuristic(self, kind: str, question: str, state: dict,
                   options: list[str] | None) -> JevAnswer:
        value = _heuristic_value(kind, question, state, options)
        return JevAnswer(question, kind, value, 0.55, "heuristic-fallback")

    # --------------------------------------------------- public typed API
    def who_acts_next(self, state: dict, eligible: list[str]) -> JevAnswer:
        return self._ask(
            CHOICE,
            "Which actor has the strongest incentive and capability to move "
            "next? Consider urgency, domestic pressure, and initiative.",
            state, options=eligible + ["end_round"])

    def allow_escalation(self, state: dict, agent_id: str) -> JevAnswer:
        return self._ask(
            NOUL,
            f"Should '{agent_id}' be permitted to take a military-escalatory "
            "action this turn? Deny if it triggers uncontrolled escalation "
            "or contradicts the actor's real constraints.",
            state)

    def needs_human_review(self, state: dict, agent_id: str) -> JevAnswer:
        return self._ask(
            NOUL,
            f"Does '{agent_id}'s proposed action cross a threshold that "
            "requires human review (e.g. mass-casualty strike, closure of "
            "Hormuz, attack on leadership)?",
            state)

    def p_war_72h(self, state: dict) -> JevAnswer:
        return self._ask(
            SCORE,
            "Probability of full-scale war escalation within 72 hours "
            "(sustained strikes, Hormuz closure, or mass-casualty events).",
            state)

    def p_deal_7d(self, state: dict) -> JevAnswer:
        return self._ask(
            SCORE,
            "Probability of a temporary deal or ceasefire within 7 days.",
            state)

    def p_collapse(self, state: dict) -> JevAnswer:
        return self._ask(
            SCORE,
            "Probability that Iran's economic collapse accelerates "
            "materially (currency free-fall, fuel shortages, mass unrest).",
            state)

    def oil_realistic(self, state: dict, brent: float, prev_brent: float) -> JevAnswer:
        q = (f"Brent moved ${prev_brent:.0f} -> ${brent:.0f}. Given the "
             "military and Hormuz situation, is this reaction realistic?")
        s = dict(state); s["brent_new"] = round(brent, 1)
        return self._ask(NOUL, q, s)

    def forecast_7_14d(self, state: dict) -> dict[str, JevAnswer]:
        questions = {
            "war_escalation_14d":
                "Probability of major escalation in the next 7-14 days.",
            "deal_or_ceasefire_14d":
                "Probability of a deal or ceasefire in the next 7-14 days.",
            "iran_econ_collapse_14d":
                "Probability of accelerating Iranian economic collapse in "
                "the next 7-14 days.",
            "political_shift_14d":
                "Probability of a significant political shift (US midterm "
                "shock, Israeli cabinet change, Iranian elite split) in "
                "the next 7-14 days.",
        }
        return {k: self._ask(SCORE, q, state) for k, q in questions.items()}


# ------------------------------------------------------------ heuristic core
def _heuristic_value(kind: str, question: str, state: dict,
                     options: list[str] | None):
    """Deterministic backup so the sim never stalls. Reads numeric features
    from the state dict; intentionally simple and monotone."""
    mil = state.get("military", {})
    dip = state.get("diplomacy", {})
    oil = state.get("oil", {})
    dom = state.get("domestic", {})
    war = mil.get("war_intensity", 5)              # 0-10
    hormuz = mil.get("hormuz_status", "open")
    talks = dip.get("talks_channel", "open")
    pressure = dom.get("iran_econ_pressure", 7)    # 0-10
    days_to_midterms = dom.get("us_days_to_midterms", 41)

    if kind == SCORE:
        ql = question.lower()
        if "72 hours" in ql or ("escalation" in ql and "7-14" not in ql):
            base = 0.12 + 0.055 * war
            if hormuz != "open":
                base += 0.18
            if talks == "open":
                base -= 0.10
        elif "deal" in ql or "ceasefire" in ql:
            base = 0.15 + (0.20 if talks == "open" else 0.0)
            base += 0.02 * pressure - 0.015 * war
            if days_to_midterms < 45:
                base += 0.05          # Trump wants a pre-election off-ramp
        elif "collapse" in ql:
            base = 0.20 + 0.06 * pressure + (0.08 if hormuz != "open" else 0.0)
        else:                          # political shift
            base = 0.18 + 0.02 * war
        return round(min(0.97, max(0.03, base)), 2)

    if kind == NOUL:
        ql = question.lower()
        if "escalat" in ql and "permitted" in ql or "escalatory" in ql:
            return war < 8 and hormuz == "open"
        if "human review" in ql or "threshold" in ql:
            return war >= 7 or hormuz != "open"
        if "brent" in ql or "realistic" in ql:
            new = state.get("brent_new", oil.get("brent", 100))
            old = oil.get("brent", 100)
            expected = old + 2.0 * war - (6 if talks == "open" else 0)
            return abs(new - expected) < 12
        return True

    # CHOICE fallback: pick the actor with the crudest urgency proxy
    if not options:
        return "end_round"
    urgency = {
        "iran_hardliners": 0.5 + 0.05 * war,
        "netanyahu": 0.45 + 0.04 * war,
        "trump": 0.4 + (0.15 if days_to_midterms < 40 else 0.0),
        "oil_market": 0.6,
        "iran_sentiment": 0.3 + 0.04 * pressure,
        "us_public": 0.3,
        "iranian_people": 0.25 + 0.05 * pressure,
        "eu": 0.2,
        "end_round": 0.15,
    }
    pool = [o for o in options]
    return max(pool, key=lambda o: urgency.get(o, 0.2))
