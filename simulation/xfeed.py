"""X/Twitter feed — the posts agents see and must reference when they speak.

Posts are seeded per round to be *realistic* (plausible handles, plausible
content given the Sept-2026 context). Agents are instructed to cite at least
one by handle. Add posts to ROUND_POSTS to steer later rounds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class XPost:
    handle: str
    text: str
    tags: frozenset[str] = frozenset()   # agent ids this is most relevant to

    def fmt(self) -> str:
        return f"@{self.handle}: {self.text}"


ROUND_POSTS: dict[int, list[XPost]] = {
    1: [
        XPost("realDonaldTrump",
              "Iran can make a DEAL and rebuild, or they can be ANNIHILATED. "
              "Their choice. Witkoff and Jared are doing a GREAT job at the UN. "
              "Gas prices coming down soon, mark my words!",
              frozenset({"trump", "us_public", "eu", "oil_market"})),
        XPost("netanyahu",
              "There will be no agreement that leaves a single centrifuge "
              "spinning in Iran. Israel will finish the job — alone if needed.",
              frozenset({"netanyahu", "iran_hardliners", "eu"})),
        XPost("khamenei_ir_fa",
              "The martyred Leader's path continues. The enemy demands our "
              "surrender dressed as negotiation. Iran does not surrender. "
              "— Office of the Supreme Leader",
              frozenset({"iran_hardliners", "iran_public"})),
        XPost("MEKhbar",
              "Tehran bazaar shut again today. Rial at 1.65M/dollar on the "
              "open market. People are selling gold teeth for bread. #Iran",
              frozenset({"iran_public", "iran_hardliners", "humanitarian"})),
        XPost("IranIntl_En",
              "Sources: IRGC-Quds pushing Mojtaba for a 'decisive' Hormuz move "
              "before US midterms; civilian cabinet resisting. #Iran",
              frozenset({"iran_hardliners", "iran_public", "oil_market"})),
        XPost("markets",
              "Brent $100.2 (+1.4%). War-risk premium now ~$18/bbl, Hormuz "
              "insurance rates at 6-month highs. Tanker traffic -22% WoW.",
              frozenset({"oil_market", "trump", "eu", "us_public",
                         "markets", "shipping", "gas_market"})),
        XPost("JavierBlas",
              "If Hormuz closes even partially for a week, $130 Brent is "
              "the floor, not the ceiling. SPR is already 40% drawn down.",
              frozenset({"oil_market", "trump", "eu"})),
        XPost("vonderleyen",
              "Europe cannot absorb another energy shock. We urge all parties "
              "to convert the UNGA contacts into a structured ceasefire track.",
              frozenset({"eu", "oil_market"})),
        XPost("amanpour",
              "UNGA hallways: both delegations deny 'negotiations', both "
              "confirm 'contact'. Diplomatic jargon doing heavy lifting.",
              frozenset({"eu", "us_public", "media"})),
        XPost("GStephanopoulos",
              "NEW POLL: 58% of voters say gas prices are their top issue; "
              "only 34% back continued strikes on Iran. GOP internal numbers "
              "worse. #Midterms",
              frozenset({"us_public", "trump"})),
        XPost("charliekirk11",
              "We didn't vote for 'manageable war'. Finish the job, Mr. "
              "President — or bring them home. This half-war is the worst "
              "option.",
              frozenset({"us_public", "trump"})),
        XPost("afshin_tehran",
              "7 months of war. My cousin's pharmacy has no insulin. The "
              "regime blames America, America bombs, we starve. Who exactly "
              "is winning? [fa]",
              frozenset({"iran_public", "israeli_public"})),
        XPost("bariweiss",
              "The 'annihilate or deal' framing leaves no room for what Iran "
              "will actually accept. Watch the Hormuz insurance market, not "
              "the speeches.",
              frozenset({"us_public", "eu", "oil_market"})),
        XPost("SecRubio",
              "Maximum pressure continues until Iran chooses to be a normal "
              "nation. All options remain on the table.",
              frozenset({"trump", "iran_hardliners", "eu"})),
        XPost("Radio_Farda",
              "Bread queues in Shiraz and Mashhad reported; Basij deploying "
              "around university campuses ahead of Friday prayers. [fa]",
              frozenset({"iran_public", "humanitarian"})),
        XPost("SpokespersonCHN",
              "China calls for maximum restraint and opposes unilateral "
              "measures that escalate tensions. Beijing stands ready to "
              "host contacts between the parties at any time. #Hormuz",
              frozenset({"china", "eu", "iran_hardliners", "oil_market"})),
        XPost("ReutersEnergy",
              "China's teapot refiners are buying discounted Iranian crude "
              "via yuan-settled channels again — volumes up 30% since the "
              "blockade tightened, per tanker trackers.",
              frozenset({"china", "oil_market", "iran_hardliners"})),
        XPost("mfa_russia",
              "Washington's 'binary choice' is gangster diplomacy. Russia "
              "will veto any UNSC cover for further aggression and is "
              "ready to discuss air-defence cooperation with Tehran.",
              frozenset({"russia", "iran_hardliners", "trump", "eu"})),
        XPost("TASS_agency",
              "Lavrov: every US carrier day in the Gulf is a day not spent "
              "elsewhere. Moscow 'wishes our American colleagues stamina'.",
              frozenset({"russia", "us_public", "trump"})),
        XPost("KSAMOFA",
              "The Kingdom urges de-escalation. Saudi Arabia is raising "
              "East-West pipeline throughput to keep crude flowing to "
              "markets regardless of Hormuz.",
              frozenset({"gulf", "oil_market", "eu", "trump"})),
        XPost("JavierBlas",
              "OPEC watch: Riyadh holds ~3mb/d spare. The price for opening "
              "the taps won't be money — it will be a US security "
              "guarantee with teeth.",
              frozenset({"gulf", "oil_market", "trump"})),
        XPost("MOFA_Taiwan",
              "Taiwan supports the international coalition's efforts to "
              "restore stability. We note reports of munitions stockpiles "
              "being drawn down for Gulf operations.",
              frozenset({"taiwan", "trump", "china"})),
        XPost("RTErdogan",
              "Turkey is ready to host the parties in Istanbul. We warned "
              "for months this escalation would price everyone out of "
              "peace. Ankara's door is open to all sides.",
              frozenset({"turkey", "eu", "iran_hardliners", "trump"})),
        XPost("haaretzcom",
              "Reservist call-up fatigue deepens: 40% of tech firms report "
              "staff shortages; northern residents still displaced after "
              "7 months. Poll: majority want 'victory or an end'.",
              frozenset({"israeli_public", "netanyahu"})),
        XPost("UNOCHA",
              "Access update: fuel deliveries to southern Iran hospitals "
              "remain blocked; estimated 310,000 internally displaced; "
              "medicine stockouts reported in 12 provinces.",
              frozenset({"humanitarian", "iran_public", "eu"})),
        XPost("business",
              "Fed watch: energy shock meets slowing payrolls — traders "
              "price a knife-edge hold; 'supply shocks can't be fixed "
              "with rate cuts' says one governor.",
              frozenset({"central_banks", "markets", "us_public"})),
        XPost("Osinttechnical",
              "Viral tonight: IRGCN small-boat swarm footage vs CENTCOM "
              "denial of a boarding attempt. Both narratives are "
              "circulating; the truth is doing push-ups.",
              frozenset({"media", "us_public", "iran_public"})),
    ],
}

DEFAULT_POSTS: list[XPost] = [
    XPost("markets",
          "Brent drifting on thin liquidity; war premium intact pending "
          "Hormuz clarity.", frozenset({"oil_market"})),
]


def feed_for(round_no: int, agent_id: str, limit: int = 6) -> list[XPost]:
    posts = ROUND_POSTS.get(round_no, DEFAULT_POSTS)
    tagged = [p for p in posts if agent_id in p.tags]
    rest = [p for p in posts if agent_id not in p.tags]
    return (tagged + rest)[:limit]
