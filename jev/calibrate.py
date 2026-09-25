"""Post-hoc calibration of Jev's raw scores against realized outcomes.

Small System-1 models anchor on a prior (in practice, scores cluster
around ~0.23 regardless of state). The calibrator keeps Jev's raw call
but corrects it with two signals from the simulation's own history:

  * bias — mean(raw_score - realized_event) over past days
  * base — empirical frequency of the event so far

    calibrated = clamp(0.75 * (raw - 0.5 * bias) + 0.25 * base_rate)

With fewer than MIN_PAIRS scored days it returns the raw value
untouched, so calibration only ever uses demonstrated track record.
"""

from __future__ import annotations

MIN_PAIRS = 2

_HORMUZ_RANK = {"open": 0, "threatened": 1,
                "partially_closed": 2, "closed": 3}


def _war_happened(prev: dict, nxt: dict) -> bool:
    """War escalation: intensity jumped, or Hormuz degraded a step."""
    return ((nxt.get("war", 0) - prev.get("war", 0) >= 0.5)
            or (_HORMUZ_RANK.get(nxt.get("hormuz", ""), 1)
                > _HORMUZ_RANK.get(prev.get("hormuz", ""), 1)))


def _deal_happened(prev: dict, nxt: dict) -> bool:
    """De-escalation: intensity fell or the market relaxed hard."""
    return ((nxt.get("war", 0) <= prev.get("war", 0) - 0.5)
            or (nxt.get("brent", 0) <= prev.get("brent", 0) - 8))


def _collapse_happened(prev: dict, nxt: dict) -> bool:
    """Iran collapse accelerated: econ pressure or street unrest jumped."""
    return ((nxt.get("econ_pressure", 0)
             - prev.get("econ_pressure", 0) >= 0.4)
            or (nxt.get("protests", 0) - prev.get("protests", 0) >= 0.5))


def _petrol_spike_happened(prev: dict, nxt: dict) -> bool:
    """French pump petrol rose >5% day over day (fast pass-through)."""
    p, n = prev.get("fr_petrol", 0), nxt.get("fr_petrol", 0)
    return bool(p) and (n - p) / p >= 0.05


def _supply_disruption_happened(prev: dict, nxt: dict) -> bool:
    """Physical supply shock: Hormuz degraded, incident surge, or a
    violent Brent gap-up."""
    return (_war_happened(prev, nxt)
            or (nxt.get("brent", 0) - prev.get("brent", 0) >= 10))


_REALIZED = {
    "p_war_72h": _war_happened,
    "p_deal_7d": _deal_happened,
    "p_collapse": _collapse_happened,
    "petrol_spike_30d": _petrol_spike_happened,
    "supply_disruption_14d": _supply_disruption_happened,
}


def _clamp(x: float) -> float:
    return min(0.97, max(0.02, x))


class JevCalibrator:
    """Recalibrates Jev scores using the simulation's own outcome log."""

    def __init__(self, history: list[dict]):
        self.history = history or []

    def pairs(self, metric: str) -> list[tuple[float, bool]]:
        """(raw score Jev gave on day d, did the event happen on d+1)."""
        realized = _REALIZED.get(metric)
        if not realized:
            return []
        out = []
        for prev, nxt in zip(self.history, self.history[1:]):
            score = prev.get(metric)
            if score is not None:
                out.append((float(score), realized(prev, nxt)))
        return out

    def calibrate(self, metric: str, raw: float) -> tuple[float, dict]:
        pairs = self.pairs(metric)
        info = {"n": len(pairs), "raw": round(raw, 3)}
        if len(pairs) < MIN_PAIRS:
            return raw, info
        bias = sum(s - float(o) for s, o in pairs) / len(pairs)
        base = sum(float(o) for _, o in pairs) / len(pairs)
        cal = _clamp(0.75 * (raw - 0.5 * bias) + 0.25 * base)
        info.update({"bias": round(bias, 3), "base": round(base, 3),
                     "calibrated": round(cal, 3)})
        return cal, info
