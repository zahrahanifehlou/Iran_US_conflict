"""Typed answers for the Jev decision layer.

Jev never writes prose. Every question returns exactly one of:

  CHOICE  -> one string out of a fixed option set  (e.g. who acts next)
  NOUL    -> boolean yes/no                        (e.g. escalation permitted)
  SCORE   -> calibrated probability in [0, 1]      (e.g. P(full-scale war))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["choice", "noul", "score"]

CHOICE = "choice"
NOUL = "noul"
SCORE = "score"


@dataclass
class JevAnswer:
    question: str
    kind: Kind
    value: Any            # str (choice) | bool (noul) | float (score)
    confidence: float     # Jev's self-reported calibration, 0..1
    source: str           # model name, or "heuristic-fallback"

    def fmt(self) -> str:
        if self.kind == NOUL:
            v = "YES" if self.value else "NO"
        elif self.kind == SCORE:
            v = f"{self.value:.2f}"
        else:
            v = str(self.value)
        tag = "" if self.source != "heuristic-fallback" else "  [fallback]"
        return f"{v}  (conf {self.confidence:.2f}){tag}"


@dataclass
class TurnGate:
    """Per-agent gate decided by Jev before the agent speaks."""
    agent_id: str
    escalation_allowed: JevAnswer
    human_review: JevAnswer


@dataclass
class RoundVerdict:
    """Everything Jev decided during one round, for logging/serialization."""
    acting_order: list[str] = field(default_factory=list)
    gates: dict[str, TurnGate] = field(default_factory=dict)
    p_war_72h: JevAnswer | None = None
    p_deal_7d: JevAnswer | None = None
    p_collapse: JevAnswer | None = None
    oil_realistic: JevAnswer | None = None
    forecast: dict[str, JevAnswer] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def ser(a: JevAnswer | None):
            return None if a is None else {
                "kind": a.kind, "value": a.value,
                "confidence": round(a.confidence, 3), "source": a.source,
            }
        return {
            "acting_order": self.acting_order,
            "gates": {
                k: {
                    "escalation_allowed": ser(g.escalation_allowed),
                    "human_review": ser(g.human_review),
                } for k, g in self.gates.items()
            },
            "p_war_72h": ser(self.p_war_72h),
            "p_deal_7d": ser(self.p_deal_7d),
            "p_collapse": ser(self.p_collapse),
            "oil_realistic": ser(self.oil_realistic),
            "forecast_7_14d": {k: ser(v) for k, v in self.forecast.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
