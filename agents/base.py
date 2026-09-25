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
    def __init__(self, persona: Persona, fast: bool = False):
        self.p = persona
        self.model = (config.FAST_MODEL if fast
                      else persona.model or config.AGENT_MODEL)

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
                         "LOGIC", "REASONING"):
                action.fields[key.lower()] = val
        return action
