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
        # ---- prediction ledger (persists across days) ----------------
        self.pending: list[dict] = []      # unresolved dated predictions
        self.pred_stats: dict = self._fresh_stats()

    @staticmethod
    def _fresh_stats() -> dict:
        return {"n": 0, "brier": 0.0, "hits": 0, "misses": 0,
                "false_pos": 0, "false_neg": 0,
                "by_horizon": {}, "by_source": {}, "conf_bins": {}}

    def record_result(self, pred: dict) -> None:
        """Fold a resolved prediction into the running metrics."""
        conf, outcome = float(pred["conf"]), float(pred["outcome"])
        hit = bool(pred["hit"])
        s = self.pred_stats
        s["n"] += 1
        s["brier"] += pred["brier"]
        s["hits" if hit else "misses"] += 1
        if pred["conf"] >= 0.5 and not outcome:
            s["false_pos"] += 1
        elif pred["conf"] < 0.5 and outcome:
            s["false_neg"] += 1
        h = s["by_horizon"].setdefault(pred["horizon"],
                                       {"n": 0, "brier": 0.0, "hits": 0})
        h["n"] += 1; h["brier"] += pred["brier"]; h["hits"] += int(hit)
        src = pred.get("source") or "unknown"
        b = s["by_source"].setdefault(src,
                                      {"n": 0, "brier": 0.0, "hits": 0})
        b["n"] += 1; b["brier"] += pred["brier"]; b["hits"] += int(hit)
        bidx = min(4, int(conf * 5))            # 0-.2, .2-.4, ... .8-1.0
        cb = s["conf_bins"].setdefault(
            str(bidx), {"n": 0, "conf": 0.0, "freq": 0.0})
        cb["n"] += 1; cb["conf"] += conf; cb["freq"] += outcome

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
            escalation_allowed: bool, transcript: list[str],
            live_wire: list[str] | None = None) -> AgentAction:
        feed = "\n".join(f"  {p.fmt()}" for p in posts)
        wire = ""
        if live_wire:
            wire = ("LIVE WIRE — real-world headlines right now (treat as "
                    "actual events unfolding in parallel):\n"
                    + "\n".join(f"  - {h}" for h in live_wire) + "\n\n")
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
            f"{wire}"
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
            elif key.startswith("PRED_"):
                # "claim text | 65" or "claim text | 0.65" or bare claim
                m = re.search(r"[|—-]\s*([\d.]+)\s*%?\s*$", val)
                claim, conf = val, 0.5
                if m:
                    conf = float(m.group(1))
                    conf = conf / 100 if conf > 1 else conf
                    claim = val[:m.start()].rstrip(" |—-:") or val
                action.fields[key.lower()] = {
                    "claim": claim.strip(),
                    "conf": min(1.0, max(0.05, conf)),
                }
            elif key == "SOURCE":
                action.fields["source"] = val.split()[0].lower().strip("|,")
            elif key in ("INSURANCE", "GOLD", "TTF", "FR_PETROL",
                         "FR_DIESEL"):
                m = re.search(r"[\d.]+", val.replace(",", ""))
                if m:
                    action.fields[key.lower()] = float(m.group(0))
            elif key in ("FREIGHT", "SPX_DIR", "NARRATIVE", "VIRAL",
                         "FOG", "CASUALTIES", "DISPLACED", "ACCESS",
                         "RATE_SIGNAL"):
                action.fields[key.lower()] = val
        return action

    # -------------------------------------------------------- learning
    def learn(self, day_label: str, ground_truth: str,
              state: SituationState,
              resolved: list[dict] | None = None) -> AgentAction:
        """Midnight cycle: see graded predictions, extract lessons, file
        new multi-horizon predictions with confidences."""
        prev = self.last_prediction or {}
        results_block = ""
        if resolved:
            lines = ["YOUR PREDICTIONS THAT JUST RESOLVED:"]
            for p in resolved:
                mark = "CORRECT" if p["hit"] else "WRONG"
                lines.append(
                    f"  - [{p['horizon']}] '{p['claim'][:80]}' -> {mark} "
                    f"(you gave {p['conf']:.0%}, it "
                    f"{'happened' if p['outcome'] else 'did not happen'})")
            results_block = "\n".join(lines) + "\n\n"
        user = (
            f"MIDNIGHT — {day_label} IS OVER.\n\n"
            f"WHAT ACTUALLY HAPPENED TODAY:\n{ground_truth}\n\n"
            f"{results_block}"
            f"STATE NOW:\n{state.human_summary()}\n\n"
            + (f"YOUR HEADLINE PREDICTION FROM LAST NIGHT: "
               f"{prev.get('prediction', 'none')} "
               f"(p_war {prev.get('p_war', '?')}/10, "
               f"brent {prev.get('brent_dir', '?')})\n\n" if prev else "")
            + "Reflect coldly: what did today prove or disprove about the "
            "other actors' incentives and constraints? Update your beliefs, "
            "then file predictions for the horizons below — put real "
            "confidence numbers on them; you will be graded.\n\n"
            "Respond in EXACTLY this format:\n"
            "LEARNED: <the sharpest lesson from today's real outcome, "
            "1 sentence>\n"
            "BELIEF: <your updated working belief about how this conflict "
            "works, 1 sentence>\n"
            "STANCE: <your posture going forward — e.g. more hawkish / "
            "more desperate / patient / opportunistic, few words>\n"
            "PREDICTION: <your single most confident call for tomorrow>\n"
            "PRED_24H: <concrete falsifiable event claim> | <0-100>\n"
            "PRED_72H: <concrete falsifiable event claim> | <0-100>\n"
            "PRED_7D: <concrete falsifiable event claim> | <0-100>\n"
            "PRED_14D: <concrete falsifiable event claim> | <0-100>\n"
            "PRED_30D: <concrete falsifiable event claim> | <0-100>\n"
            "SOURCE: <the input that drove your calls most: xfeed | "
            "wire | markets | memory | transcript>\n"
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
        # ---- file this night's horizon predictions into the ledger ----
        from simulation.predictions import HORIZON_DAYS
        src = upd.fields.get("source", "")
        for key, days in HORIZON_DAYS.items():
            p = upd.fields.get(f"pred_{key}")
            if p and p.get("claim"):
                self.pending.append({
                    "made": state.round_no, "due": state.round_no + days,
                    "horizon": key, "claim": p["claim"], "conf": p["conf"],
                    "source": src, "status": "pending"})
        self.pending = self.pending[-40:]
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
