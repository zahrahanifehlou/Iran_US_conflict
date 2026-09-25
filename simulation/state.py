"""SituationState — the world as the Director sees it at the top of a round."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class SituationState:
    round_no: int
    date_range: str
    day_of_war: int

    # --- military ---
    war_intensity: float = 5.5            # 0 = ceasefire, 10 = total war
    hormuz_status: str = "threatened"     # open | threatened | partially_closed | closed
    recent_strikes: list[str] = field(default_factory=list)
    tanker_incidents_7d: int = 1

    # --- diplomacy ---
    talks_channel: str = "open"           # open | frozen | collapsed
    deal_on_table: str = "none"           # none | framework | ceasefire | comprehensive
    unga_contact: bool = True             # Witkoff/Kushner channel active

    # --- oil & markets ---
    brent: float = 100.0
    brent_forecast: float = 104.0
    wti: float = 95.5                     # Brent-WTI spread widens in crisis
    gold: float = 2650.0                  # safe-haven barometer
    ttf_gas: float = 38.0                 # EU natural gas, EUR/MWh
    hormuz_insurance: float = 2.5         # war-risk premium, % of hull value
    us_gas_price: float = 4.35            # $/gal national average

    # --- real-world impact layer: French pump prices (EUR/L) ---
    fr_petrol: float = 2.22               # SP95-E10 pump price (Sep-2026 anchor)
    fr_diesel: float = 2.38               # gazole pump price (Sep-2026 anchor)
    fr_fuel_rebate: float = 0.0           # govt rebate / tax cut (EUR/L)

    # --- domestic politics ---
    us_days_to_midterms: int = 40
    us_approval_trump: float = 0.44
    us_war_support: float = 0.38
    iran_inflation: float = 0.62          # annualised, ~62%
    rial_black_market: float = 1_650_000  # per USD
    iran_protest_level: float = 4.0       # 0-10 street mobilisation
    iran_econ_pressure: float = 7.5       # 0-10 composite
    regime_stability: float = 0.58        # 0-1 elite cohesion
    israel_coalition_stress: float = 0.4

    # --- narrative ---
    headlines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Compact dict fed to Jev (kept small — System-1 models are tiny)."""
        return {
            "round": self.round_no,
            "day_of_war": self.day_of_war,
            "military": {
                "war_intensity": self.war_intensity,
                "hormuz_status": self.hormuz_status,
                "tanker_incidents_7d": self.tanker_incidents_7d,
            },
            "diplomacy": {
                "talks_channel": self.talks_channel,
                "deal_on_table": self.deal_on_table,
                "unga_contact": self.unga_contact,
            },
            "oil": {
                "brent": round(self.brent, 1),
                "brent_forecast": round(self.brent_forecast, 1),
                "wti": round(self.wti, 1),
                "gold": round(self.gold, 0),
                "ttf_gas": round(self.ttf_gas, 1),
                "hormuz_insurance_pct": round(self.hormuz_insurance, 1),
                "us_gas_price": self.us_gas_price,
                "fr_petrol_eur_l": round(self.fr_petrol, 3),
                "fr_diesel_eur_l": round(self.fr_diesel, 3),
                "fr_fuel_rebate": round(self.fr_fuel_rebate, 2),
            },
            "domestic": {
                "us_days_to_midterms": self.us_days_to_midterms,
                "us_approval_trump": self.us_approval_trump,
                "us_war_support": self.us_war_support,
                "iran_inflation": self.iran_inflation,
                "iran_protest_level": self.iran_protest_level,
                "iran_econ_pressure": self.iran_econ_pressure,
                "regime_stability": self.regime_stability,
            },
        }

    def human_summary(self) -> str:
        lines = [
            f"ROUND {self.round_no}  |  {self.date_range}  |  Day ~{self.day_of_war} of the war",
            "",
            "MILITARY",
            f"  War intensity {self.war_intensity}/10 | Strait of Hormuz: "
            f"{self.hormuz_status.replace('_', ' ')} | "
            f"tanker incidents (7d): {self.tanker_incidents_7d}",
        ]
        for s in self.recent_strikes[-3:]:
            lines.append(f"  - {s}")
        lines += [
            "",
            "DIPLOMACY",
            f"  Talks channel: {self.talks_channel} | deal on table: {self.deal_on_table}"
            + (" | UNGA sideline contact active" if self.unga_contact else ""),
            "",
            "OIL & MARKETS",
            f"  Brent ${self.brent:.1f}/bbl (forecast ${self.brent_forecast:.1f}) | "
            f"WTI ${self.wti:.1f} | US gas ${self.us_gas_price:.2f}/gal",
            f"  Gold ${self.gold:,.0f}/oz | TTF gas EUR{self.ttf_gas:.0f}/MWh | "
            f"Hormuz war-risk insurance {self.hormuz_insurance:.1f}% of hull",
            f"  FR pump: petrol EUR{self.fr_petrol:.2f}/L | diesel "
            f"EUR{self.fr_diesel:.2f}/L"
            + (f" | govt rebate -EUR{self.fr_fuel_rebate:.2f}/L"
               if self.fr_fuel_rebate > 0.01 else ""),
            "",
            "DOMESTIC",
            f"  US: {self.us_days_to_midterms}d to midterms | Trump approval "
            f"{self.us_approval_trump:.0%} | war support {self.us_war_support:.0%}",
            f"  IR: inflation {self.iran_inflation:.0%} | rial {self.rial_black_market:,.0f}/USD "
            f"| protests {self.iran_protest_level}/10 | regime cohesion {self.regime_stability:.0%}",
        ]
        for h in self.headlines[-4:]:
            lines.append(f"  * {h}")
        return "\n".join(lines)


def _advance_date_range(s: SituationState) -> None:
    """'25-26 September 2026' -> '26-27 September 2026'."""
    import re
    m = re.match(r"(\d+)-(\d+)\s+(\w+)\s+(\d{4})", s.date_range)
    if m:
        d1, d2, month, year = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        s.date_range = f"{d2}-{d2 + 1} {month} {year}"
    s.day_of_war += 1


def state_from_full(d: dict) -> SituationState:
    """Rebuild a SituationState from a dumped asdict(). Unknown keys are
    ignored so old dumps still load."""
    fields = SituationState.__dataclass_fields__
    return SituationState(**{k: v for k, v in d.items() if k in fields})


def initial_state() -> SituationState:
    """25–26 September 2026 — the seeded real-world context."""
    return SituationState(
        round_no=1,
        date_range="25-26 September 2026",
        day_of_war=217,   # ~7 months in
        war_intensity=5.5,
        hormuz_status="threatened",
        recent_strikes=[
            "IDF drones hit IRGC radar site near Isfahan (limited damage)",
            "Iranian proxies launched rockets at US base in Erbil; no fatalities",
            "US Navy escorted 3 tankers through Hormuz under IRGCN harassment",
        ],
        talks_channel="open",
        deal_on_table="framework",
        unga_contact=True,
        brent=100.0,
        brent_forecast=104.0,
        us_gas_price=4.35,
        us_days_to_midterms=40,
        headlines=[
            "Trump at UNGA: 'binary choice — a deal that lets Iran rebuild, "
            "or we annihilate the Islamic Republic'",
            "Witkoff/Kushner met Iranian officials on UNGA sidelines",
            "Mojtaba Khamenei consolidates as Supreme Leader; IRGC dominates "
            "war cabinet",
            "IAEA: Iran retains ~60% enriched stockpile at unknown sites",
        ],
    )
