"""World-update rules — how agent actions move the state between rounds.

The oil agent's Brent call is taken as the market's raw vote; if Jev judges
it unrealistic, a deterministic fair-value model overrides it instead.
"""

from __future__ import annotations

from simulation.state import SituationState

HORMUZ_PREMIUM = {
    "open": 0.0,
    "threatened": 18.0,
    "partially_closed": 35.0,
    "closed": 60.0,
}


def fair_brent(state: SituationState) -> float:
    """Model price: baseline + Hormuz premium + intensity + incidents."""
    base = 82.0
    prem = HORMUZ_PREMIUM.get(state.hormuz_status, 18.0)
    return base + prem + 1.2 * state.war_intensity + 2.0 * state.tanker_incidents_7d


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def apply_market(state: SituationState, brent_call: float | None,
                 forecast_call: float | None, realistic: bool) -> None:
    fair = fair_brent(state)
    prev = state.brent
    if brent_call is not None and realistic:
        # market vote accepted, but mean-revert a bit toward fair value
        state.brent = clamp(0.5 * brent_call + 0.5 * fair, 70, 180)
    else:
        state.brent = clamp(fair + 0.25 * (prev - fair), 70, 180)
    state.brent_forecast = clamp(
        forecast_call if forecast_call is not None else fair + 4, 70, 200)
    # gas price lags Brent roughly $0.024/gal per $1 crude
    state.us_gas_price = clamp(3.10 + 0.024 * (state.brent - 70), 2.5, 7.5)


def apply_actions(state: SituationState, actions) -> list[str]:
    """Nudge state variables from parsed agent actions. Returns change notes."""
    notes = []
    text = " ".join(
        f"{a.statement} {a.proposed_action}" for a in actions).lower()

    def hit(*words):
        return any(w in text for w in words)

    if hit("hormuz", "strait", "tanker", "blockade", "mine"):
        if hit("close", "closing", "shut", "mine"):
            state.hormuz_status = "partially_closed"
            state.tanker_incidents_7d += 2
            state.war_intensity = clamp(state.war_intensity + 1.0, 0, 10)
            notes.append("Hormuz threatened with closure -> partially closed")
        else:
            state.tanker_incidents_7d += 1
            notes.append("Hormuz pressure rises (tanker incident)")

    if hit("strike", "bomb", "missile", "attack", "hit ", "target"):
        state.war_intensity = clamp(state.war_intensity + 0.5, 0, 10)
        state.recent_strikes.append(
            f"R{state.round_no}: new kinetic action claimed")
        notes.append("War intensity up on new strikes")

    if hit("ceasefire", "deal", "talks", "negotiat", "freeze", "escrow",
           "framework", "de-escalat"):
        state.war_intensity = clamp(state.war_intensity - 0.6, 0, 10)
        state.talks_channel = "open"
        if state.deal_on_table == "none":
            state.deal_on_table = "framework"
        notes.append("Diplomatic track strengthened")

    if hit("sanction", "snapback", "export ban"):
        state.iran_econ_pressure = clamp(state.iran_econ_pressure + 0.4, 0, 10)
        notes.append("Iranian economic pressure up")

    if hit("protest", "riot", "bazaar shut", "strike action"):
        state.iran_protest_level = clamp(state.iran_protest_level + 0.6, 0, 10)
        state.regime_stability = clamp(state.regime_stability - 0.03, 0, 1)
        notes.append("Iranian street pressure rising")

    # slow structural drift
    state.iran_econ_pressure = clamp(state.iran_econ_pressure + 0.15, 0, 10)
    state.regime_stability = clamp(
        state.regime_stability - 0.01 + 0.02 * (10 - state.iran_protest_level) / 10,
        0.05, 0.98)
    state.iran_protest_level = clamp(
        state.iran_protest_level + 0.1 * (state.iran_econ_pressure - 5), 0, 10)
    state.rial_black_market *= 1 + 0.01 * state.iran_econ_pressure
    state.us_days_to_midterms = max(0, state.us_days_to_midterms - 1)
    state.us_war_support = clamp(
        state.us_war_support - 0.01 * (state.us_gas_price - 4.0), 0.1, 0.9)
    state.us_approval_trump = clamp(
        0.30 + 0.5 * state.us_war_support - 0.02 * (state.war_intensity - 5),
        0.15, 0.75)

    return notes
