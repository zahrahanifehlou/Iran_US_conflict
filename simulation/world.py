"""World-update rules — how agent actions move the state.

Per-step updates (`apply_single_action`) run after every agent acts so the
round can be animated as a trajectory. Structural drift
(`end_of_round_drift`) and the oil-market settlement (`apply_market`) run
once per round. The oil agent's Brent call is the market's raw vote; if Jev
judges it unrealistic, the fair-value model overrides it.
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


def gas_from_brent(brent: float) -> float:
    """Pump price lags crude ~$0.024/gal per $1 above $70 oil."""
    return clamp(3.10 + 0.024 * (brent - 70), 2.5, 7.5)


INSURANCE_BASE = {          # war-risk premium, % of hull value per transit
    "open": 0.6,
    "threatened": 2.5,
    "partially_closed": 6.0,
    "closed": 12.0,
}


def _fair_gold(state: SituationState) -> float:
    return 1900 + 110 * state.war_intensity + 200 * (state.hormuz_status != "open")


def _fair_insurance(state: SituationState) -> float:
    base = INSURANCE_BASE.get(state.hormuz_status, 2.5)
    return base + 0.35 * state.tanker_incidents_7d


def tick_markets(state: SituationState, weight: float = 0.30) -> None:
    """Secondary markets shadow Brent: WTI spread, gold, war-risk insurance."""
    state.wti = clamp(state.brent - 4.2 - 0.15 * state.hormuz_insurance,
                      60, 175)
    state.gold = clamp(
        state.gold + weight * (_fair_gold(state) - state.gold), 1500, 4500)
    state.hormuz_insurance = clamp(
        state.hormuz_insurance + weight *
        (_fair_insurance(state) - state.hormuz_insurance), 0.4, 20)


def tick_brent(state: SituationState, weight: float = 0.30) -> None:
    """Intra-round: market drifts part-way toward fair value after each act."""
    state.brent = clamp(
        state.brent + weight * (fair_brent(state) - state.brent), 70, 180)
    state.us_gas_price = gas_from_brent(state.brent)
    tick_markets(state, weight)


def apply_single_action(state: SituationState, action) -> list[str]:
    """Keyword-driven state nudges from ONE agent's action. Returns notes."""
    notes = []
    text = f"{action.statement} {action.proposed_action}".lower()

    def hit(*words):
        return any(w in text for w in words)

    if hit("hormuz", "strait", "tanker", "blockade", "mine"):
        if hit("close", "closing", "shut", "mine"):
            state.hormuz_status = "partially_closed"
            state.tanker_incidents_7d += 2
            state.war_intensity = clamp(state.war_intensity + 1.0, 0, 10)
            notes.append(f"{action.agent_id}: Hormuz -> partially closed")
        else:
            state.tanker_incidents_7d += 1
            notes.append(f"{action.agent_id}: Hormuz pressure rises")

    if hit("strike", "bomb", "missile", "attack", "hit ", "target"):
        state.war_intensity = clamp(state.war_intensity + 0.5, 0, 10)
        state.recent_strikes.append(
            f"R{state.round_no}: kinetic action by {action.agent_id}")
        notes.append(f"{action.agent_id}: war intensity up (new strikes)")

    if hit("ceasefire", "deal", "talks", "negotiat", "freeze", "escrow",
           "framework", "de-escalat", "corridor"):
        state.war_intensity = clamp(state.war_intensity - 0.5, 0, 10)
        state.talks_channel = "open"
        if state.deal_on_table == "none":
            state.deal_on_table = "framework"
        notes.append(f"{action.agent_id}: diplomatic track strengthened")

    if hit("sanction", "snapback", "export ban"):
        state.iran_econ_pressure = clamp(state.iran_econ_pressure + 0.4, 0, 10)
        notes.append(f"{action.agent_id}: Iran economic pressure up")

    if hit("protest", "riot", "bazaar shut", "strike action"):
        state.iran_protest_level = clamp(state.iran_protest_level + 0.6, 0, 10)
        state.regime_stability = clamp(state.regime_stability - 0.03, 0, 1)
        notes.append(f"{action.agent_id}: Iranian street pressure rising")

    # ---- great-power levers -------------------------------------------
    if hit("s-400", "s400", "air defence", "air defense", "arms sale",
           "military aid", "satellite targeting"):
        state.war_intensity = clamp(state.war_intensity + 0.3, 0, 10)
        state.regime_stability = clamp(state.regime_stability + 0.02, 0, 1)
        notes.append(f"{action.agent_id}: Russian-style materiel bolsters Tehran")

    if hit("yuan", "barter", "discounted crude", "buy iranian",
           "teapot refiner"):
        state.iran_econ_pressure = clamp(state.iran_econ_pressure - 0.4, 0, 10)
        state.brent = clamp(state.brent - 1.0, 70, 180)   # more barrels float
        notes.append(f"{action.agent_id}: sanctioned-crude channels ease "
                     "Iran's pressure")

    if hit("spare capacity", "raise output", "increase production",
           "opec", "east-west pipeline", "red sea terminal"):
        state.brent = clamp(state.brent - 3.0, 70, 180)
        state.hormuz_insurance = clamp(state.hormuz_insurance - 0.8, 0.4, 20)
        notes.append(f"{action.agent_id}: supply relief calms the market")

    if hit("mediat", "broker", "good offices", "beijing", "muscat",
           "istanbul", "host talks"):
        state.talks_channel = "open"
        state.war_intensity = clamp(state.war_intensity - 0.3, 0, 10)
        notes.append(f"{action.agent_id}: third-party mediation opens a track")

    # ---- market/society layer vocab ------------------------------------
    if hit("lng", "ttf", "qatar", "gas terminal", "dolphin pipeline"):
        state.ttf_gas = clamp(state.ttf_gas + 2.5, 10, 200)
        notes.append(f"{action.agent_id}: European gas reprices")

    if hit("reroute", "cape of good hope", "crew refusal", "vlcc",
           "freight"):
        state.hormuz_insurance = clamp(
            state.hormuz_insurance + 0.6, 0.4, 20)
        notes.append(f"{action.agent_id}: shipping reprices the transit risk")

    if hit("humanitarian corridor", "aid convoy", "ceasefire for aid",
           "evacuation"):
        state.talks_channel = "open"
        notes.append(f"{action.agent_id}: humanitarian pressure opens access")

    if hit("leak", "viral", "footage", "fake", "disinfo", "narrative"):
        state.iran_protest_level = clamp(
            state.iran_protest_level + 0.15, 0, 10)
        state.us_war_support = clamp(
            state.us_war_support - 0.005, 0.1, 0.9)
        notes.append(f"{action.agent_id}: information battlespace shifts")

    return notes


def end_of_round_drift(state: SituationState) -> None:
    """Slow structural pressure applied once per round."""
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
    state.us_gas_price = gas_from_brent(state.brent)
    tick_markets(state)
