"""Swarm intelligence — a second forecasting voice alongside Jev.

After the midnight learning cycle every agent has already filed
P_WAR / P_DEAL (0-10) and BRENT_DIR, so the swarm needs no extra LLM
calls. It runs a UNU-style convergence on those votes:

  * each vote is weighted by the voter's track record (prediction
    accuracy so far) — unknown agents start at a neutral weight;
  * over a few iterations every position is pulled toward the
    *weighted* consensus, but the pull is inversely proportional to
    the voter's skill: proven forecasters are sticky, unproven ones
    get dragged by the swarm;
  * the swarm settles when the largest movement falls below epsilon
    (or iterations run out). The residual spread is the honest measure
    of how much the group still disagrees.

The result is stored in the day's dump next to Jev's calibrated scores —
two forecasting voices that can disagree, and the disagreement is itself
a signal. Pure stdlib, deterministic, microseconds per question.
"""

from __future__ import annotations

import math

DEFAULT_PULL = 0.35          # base attraction to the weighted mean
DEFAULT_ITERS = 12           # max convergence rounds per question
DEFAULT_EPS = 1e-4           # settle threshold on max position movement


def _skill(stats: dict) -> float:
    """Agent's forecasting skill 0..1 from its ledger; 0.5 when unproven
    (fewer than 3 graded calls)."""
    n = (stats or {}).get("n", 0)
    if n < 3:
        return 0.5
    return max(0.0, min(1.0, stats.get("hits", 0) / n))


def collect_votes(learning: dict, agents: dict) -> list[dict]:
    """Turn each agent's midnight update into a swarm vote."""
    votes = []
    for aid, upd in (learning or {}).items():
        pw, pd = upd.get("p_war"), upd.get("p_deal")
        if pw is None and pd is None:
            continue
        agent = agents.get(aid) if agents else None
        votes.append({
            "agent_id": aid,
            "p_war": _clamp01((pw or 0) / 10.0) if pw is not None else None,
            "p_deal": _clamp01((pd or 0) / 10.0) if pd is not None else None,
            "brent_dir": (upd.get("brent_dir") or "").lower() or None,
            "skill": _skill(agent.pred_stats if agent else {}),
            "n_graded": (agent.pred_stats or {}).get("n", 0) if agent else 0,
        })
    return votes


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _converge(positions: list[float], skills: list[float],
              pull: float, iters: int, eps: float) -> dict:
    """Iterated weighted-mean convergence. Positions start at the voter's
    own estimate; the pull each round is pull * (1 - skill) so high-skill
    voters resist and low-skill voters follow."""
    w = [0.5 + s for s in skills]          # proven skill pulls harder
    pos = list(positions)
    used = 0
    for used in range(1, iters + 1):
        mean = sum(p * wi for p, wi in zip(pos, w)) / max(1e-9, sum(w))
        nxt = [p + pull * (1 - s) * (mean - p)
               for p, s in zip(pos, skills)]
        moved = max(abs(a - b) for a, b in zip(pos, nxt))
        pos = nxt
        if moved < eps:
            break
    mean = sum(p * wi for p, wi in zip(pos, w)) / max(1e-9, sum(w))
    disp = (math.sqrt(sum((p - mean) ** 2 for p in pos) / len(pos))
            if len(pos) > 1 else 0.0)
    return {"value": round(mean, 3),
            "dispersion": round(disp, 3),          # 0 = unanimous
            "iters": used,
            "converged": moved < eps,
            "final_positions": [round(p, 3) for p in pos]}


def _plurality(choices: list[str], skills: list[float]) -> dict:
    """Skill-weighted plurality for categorical calls (brent direction)."""
    tally: dict[str, float] = {}
    for c, s in zip(choices, skills):
        tally[c] = tally.get(c, 0.0) + (0.5 + s)
    total = sum(tally.values()) or 1.0
    winner = max(tally, key=tally.get)
    return {"direction": winner,
            "share": round(tally[winner] / total, 3),
            "tally": {k: round(v / total, 3) for k, v in tally.items()}}


def swarm_consensus(votes: list[dict],
                    pull: float = DEFAULT_PULL,
                    iters: int = DEFAULT_ITERS,
                    eps: float = DEFAULT_EPS) -> dict:
    """Run the swarm over a day's votes. Returns a dump-ready block."""
    out: dict = {"n_voters": len(votes), "votes": votes}
    if not votes:
        out["state"] = "no votes"
        return out

    for name, key in (("p_war_72h", "p_war"), ("p_deal_7d", "p_deal")):
        ps = [v for v in votes if v[key] is not None]
        if len(ps) >= 2:
            out[name] = _converge([v[key] for v in ps],
                                  [v["skill"] for v in ps], pull, iters, eps)
            out[name]["n"] = len(ps)
        elif ps:
            out[name] = {"value": ps[0][key], "dispersion": 0.0,
                         "iters": 0, "converged": True, "n": 1}
        else:
            out[name] = {"value": None, "n": 0}

    dirs = [v for v in votes if v["brent_dir"] in ("up", "down", "flat")]
    out["brent_dir"] = (_plurality([v["brent_dir"] for v in dirs],
                                 [v["skill"] for v in dirs])
                        if dirs else {"direction": None, "n": 0})
    out["brent_dir"]["n"] = len(dirs)

    # overall conviction: how tight the group finished on the numeric calls
    disp = [out[k]["dispersion"] for k in ("p_war_72h", "p_deal_7d")
            if out[k].get("dispersion") is not None]
    out["conviction"] = (round(1 - min(1.0, 2 * sum(disp) / len(disp)), 3)
                         if disp else None)
    out["state"] = "ok"
    return out


def compare_with_jev(swarm: dict, verdict: dict) -> dict:
    """Absolute gaps between the swarm consensus and Jev's calibrated
    scores — the disagreement is itself a useful signal."""
    gaps = {}
    for key, jk in (("p_war_72h", "p_war_72h"), ("p_deal_7d", "p_deal_7d")):
        sv = (swarm.get(key) or {}).get("value")
        jv = ((verdict.get(jk) or {}).get("value"))
        if sv is not None and jv is not None:
            gaps[key] = round(abs(sv - jv), 3)
    return gaps
