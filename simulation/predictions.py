"""Prediction ledger — the eval engine behind the learning loop.

Every midnight each agent files typed predictions across five horizons:

    horizon    days
    24h        1      major escalation / de-escalation
    72h        3      attacks, ceasefire, retaliation, diplomatic moves
    7d         7      conflict intensity, Hormuz/shipping disruption
    14d        14     oil direction, policy responses
    30d        30     sanctions, negotiations, deployments, expansion risk

Loop: prediction -> stored with confidence -> matures -> observed outcome
-> Jev (or keyword fallback) judges hit/miss -> Brier + accuracy update ->
results shown back to the agent at the next learning cycle.

Metrics tracked per agent: mean Brier, accuracy, false positives/negatives,
splits by horizon and by info source, plus binned confidence vs empirical
frequency for the calibration curve.
"""

from __future__ import annotations

import re

HORIZON_DAYS = {
    "24h": 1, "72h": 3, "7d": 7, "14d": 14, "30d": 30,
}

# stop-words for the offline keyword judge
_STOP = {"will", "with", "that", "this", "from", "into", "over", "under",
         "within", "next", "days", "hours", "likely", "than", "then",
         "their", "there", "have", "been", "more", "some", "such",
         "only", "also", "very", "much", "most", "major", "new", "the",
         "and", "for", "are", "not", "all", "can", "had", "its", "may"}


def judge_claim(claim: str, truth_text: str, jev,
                offline: bool) -> bool | None:
    """Did the predicted event actually occur? Jev judges on substance;
    offline falls back to keyword overlap. None = undetermined."""
    if not offline:
        try:
            ans = jev.event_occurred(claim, truth_text)
            if ans is not None and isinstance(ans.value, bool):
                return ans.value
        except Exception:
            pass
    words = {w for w in re.findall(r"[a-z]{4,}", claim.lower())
             if w not in _STOP}
    if not words:
        return None
    low = truth_text.lower()
    hits = sum(1 for w in words if w in low)
    frac = hits / len(words)
    if frac >= 0.5:
        return True
    if hits == 0:
        return False
    return None                      # partial overlap -> undetermined


def evaluate_due(agent, today: int, truth_text: str, jev,
                 offline: bool) -> list[dict]:
    """Grade every pending prediction whose horizon has matured.
    Returns the list of newly resolved predictions (for the log + the
    agent's next prompt)."""
    resolved = []
    still_pending = []
    for p in agent.pending:
        if p["status"] != "pending":
            continue
        if p["due"] > today:
            still_pending.append(p)
            continue
        outcome = judge_claim(p["claim"], truth_text, jev, offline)
        if outcome is None:
            # past due but the record can't confirm/deny it — expire
            if today - p["due"] >= 1:
                p["status"] = "expired"
            else:
                still_pending.append(p)
            continue
        p["status"] = "resolved"
        p["outcome"] = bool(outcome)
        p["brier"] = round((p["conf"] - float(outcome)) ** 2, 4)
        p["hit"] = bool((p["conf"] >= 0.5) == outcome)
        agent.record_result(p)
        resolved.append(p)
    agent.pending = still_pending[-40:]
    return resolved


def scoreboard(agents: dict) -> dict:
    """Cumulative metrics snapshot for charts, logs and the daily post."""
    board = {}
    for aid, agent in agents.items():
        s = agent.pred_stats
        n = s.get("n", 0)
        if not n:
            continue
        board[aid] = {
            "n": n,
            "accuracy": round(s["hits"] / n, 3),
            "brier": round(s["brier"] / n, 3),
            "false_pos": s.get("false_pos", 0),
            "false_neg": s.get("false_neg", 0),
            "by_horizon": {
                h: {"n": v["n"], "acc": round(v["hits"] / v["n"], 3),
                    "brier": round(v["brier"] / v["n"], 3)}
                for h, v in s.get("by_horizon", {}).items()
            },
            "by_source": {
                src: {"n": v["n"], "acc": round(v["hits"] / v["n"], 3)}
                for src, v in s.get("by_source", {}).items()
            },
            "conf_bins": s.get("conf_bins", {}),
        }
    return board
