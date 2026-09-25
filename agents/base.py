"""Base agent: persona + Ollama generation + loose output parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
import ollama_client
from .personas import Persona
from simulation.state import SituationState
from simulation.xfeed import XPost


@dataclass
class AgentAction:
    agent_id: str
    name: str
    statement: str
    proposed_action: str = ""
    escalation_requested: bool = False
    xref: str = ""
    fields: dict = field(default_factory=dict)   # structured agents (oil/sentiment)
    raw: str = ""
    model: str = ""


class Agent:
    MEMORY_DEPTH = 4        # how many daily lessons persist in the prompt

    def __init__(self, persona: Persona, fast: bool = False):
        self.p = persona
        self.model = (config.FAST_MODEL if fast
                      else persona.model or config.AGENT_MODEL)
        # ---- learning state (persists across days) -------------------
        self.memory: list[str] = []        # cold lessons from real outcomes
        self.stance: str = ""              # current posture sentence
        self.last_prediction: dict = {}    # prediction made last midnight
        self.scorecard: dict = {"hits": 0, "misses": 0}

    def _memory_block(self) -> str:
        if not self.memory and not self.stance:
            return ""
        lines = ["YOUR ACCUMULATED LEARNING (from real outcomes):"]
        lines += [f"  - {m}" for m in self.memory[-self.MEMORY_DEPTH:]]
        if self.stance:
            lines.append(f"CURRENT POSTURE: {self.stance}")
        if self.last_prediction:
            lines.append(f"YOUR PREDICTION FOR TODAY WAS: "
                         f"{self.last_prediction.get('prediction', '?')}")
        return "\n".join(lines) + "\n\n"

    # ---------------------------------------------------------- acting
    def act(self, state: SituationState, posts: list[XPost],
            escalation_allowed: bool, transcript: list[str]) -> AgentAction:
        feed = "\n".join(f"  {p.fmt()}" for p in posts)
        prior = "\n".join(transcript[-4:]) if transcript else "  (you move first)"
        gate = (
            "Jev PERMITS escalation this turn." if escalation_allowed
            else "Jev DENIES escalation this turn — you may manoeuvre, "
                 "threaten, sanction, talk or signal, but no new military "
                 "escalation."
        )
        if "OUTPUT FORMAT" in self.p.system:
            fmt = ("Respond using ONLY the output format defined in your "
                   "instructions. It is mandatory, not optional.")
        else:
            fmt = (
                "Respond in EXACTLY this format:\n"
                "XREF: @<handle> — what it changes for you\n"
                "STATEMENT: <in-character public statement, 2-4 sentences>\n"
                "REASONING: <private incentive logic, 1-2 sentences>\n"
                "ACTION: <concrete move this turn>\n"
                "ESCALATION: request | none"
            )
        user = (
            f"SITUATION ({state.date_range}):\n{state.human_summary()}\n\n"
            f"{self._memory_block()}"
            f"RECENT X/TWITTER POSTS:\n{feed}\n\n"
            f"WHAT OTHERS JUST DID:\n{prior}\n\n"
            f"RULES: {gate} You MUST reference at least one post above by "
            f"@handle. Cold, incentive-driven reasoning — no moral lectures. "
            "Act only through the means YOUR role actually controls, and do "
            "not copy or echo another actor's proposal.\n\n"
            f"{fmt}"
        )
        raw = ollama_client.chat(
            self.model,
            [{"role": "system", "content": self.p.system},
             {"role": "user", "content": user}],
            temperature=self.p.temperature,
            num_predict=config.AGENT_NUM_PREDICT,
            think=False,
        )
        return self._parse(raw)

    def _parse(self, raw: str) -> AgentAction:
        action = AgentAction(self.p.agent_id, self.p.name, statement=raw,
                             raw=raw, model=self.model)
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().upper().replace(" ", "_")
            val = val.strip()
            if key == "XREF":
                action.xref = val
            elif key == "STATEMENT":
                action.statement = val
            elif key == "ACTION":
                action.proposed_action = val
            elif key == "ESCALATION":
                action.escalation_requested = val.lower().startswith("req")
            elif key == "BRENT":
                m = re.search(r"[\d.]+", val)
                if m:
                    action.fields["brent"] = float(m.group(0))
            elif key == "FORECAST":
                m = re.search(r"[\d.]+", val)
                if m:
                    action.fields["forecast"] = float(m.group(0))
            elif key in ("MOOD", "PROTEST_LEVEL", "WAR_FATIGUE",
                         "NATIONALISM_RALLY", "BLACK_MARKET", "SIGNAL",
                         "LOGIC", "REASONING", "LEARNED", "BELIEF",
                         "PREDICTION", "STANCE", "BRENT_DIR"):
                action.fields[key.lower()] = val
            elif key in ("P_WAR", "P_DEAL", "P_COLLAPSE"):
                m = re.search(r"[\d.]+", val)
                if m:
                    action.fields[key.lower()] = float(m.group(0))
        return action

    # -------------------------------------------------------- learning
    def learn(self, day_label: str, ground_truth: str,
              state: SituationState) -> AgentAction:
        """Midnight cycle: compare yesterday's prediction to what actually
        happened, extract a lesson, file a prediction for tomorrow."""
        prev = self.last_prediction or {}
        user = (
            f"MIDNIGHT — {day_label} IS OVER.\n\n"
            f"WHAT ACTUALLY HAPPENED TODAY:\n{ground_truth}\n\n"
            f"STATE NOW:\n{state.human_summary()}\n\n"
            + (f"YOUR PREDICTION MADE LAST NIGHT: "
               f"{prev.get('prediction', 'none')} "
               f"(p_war {prev.get('p_war', '?')}/10, "
               f"brent {prev.get('brent_dir', '?')})\n\n" if prev else "")
            + "Reflect coldly: what did today prove or disprove about the "
            "other actors' incentives and constraints? Update your beliefs, "
            "then predict tomorrow.\n\n"
            "Respond in EXACTLY this format:\n"
            "LEARNED: <the sharpest lesson from today's real outcome, "
            "1 sentence>\n"
            "BELIEF: <your updated working belief about how this conflict "
            "works, 1 sentence>\n"
            "STANCE: <your posture going forward — e.g. more hawkish / "
            "more desperate / patient / opportunistic, few words>\n"
            "PREDICTION: <your single most confident call for tomorrow>\n"
            "P_WAR: <0-10 likelihood of major escalation tomorrow>\n"
            "P_DEAL: <0-10 likelihood of a deal/ceasefire step tomorrow>\n"
            "BRENT_DIR: up | down | flat"
        )
        raw = ollama_client.chat(
            self.model,
            [{"role": "system", "content": self.p.system},
             {"role": "user", "content": user}],
            temperature=0.5,
            num_predict=280,
            think=False,
        )
        upd = self._parse(raw)

        # --- score yesterday's call against reality --------------------
        if prev:
            hit = self._grade(prev, state)
            self.scorecard["hits" if hit else "misses"] += 1

        lesson = upd.fields.get("learned", "")
        if lesson:
            self.memory.append(lesson)
            self.memory = self.memory[-8:]
        self.stance = upd.fields.get("stance", self.stance)
        self.last_prediction = {
            "prediction": upd.fields.get("prediction", ""),
            "p_war": upd.fields.get("p_war"),
            "p_deal": upd.fields.get("p_deal"),
            "brent_dir": upd.fields.get("brent_dir", "").lower(),
        }
        upd.fields["scorecard"] = dict(self.scorecard)
        upd.fields["belief"] = upd.fields.get("belief", "")
        return upd

    @staticmethod
    def _grade(pred: dict, state: SituationState) -> bool:
        """Crude correctness check on yesterday's brent direction call."""
        direction = pred.get("brent_dir", "")
        return direction in ("up", "down", "flat") and (
            (direction == "up" and state.brent >= 102) or
            (direction == "down" and state.brent <= 95) or
            (direction == "flat" and 95 < state.brent < 102))
