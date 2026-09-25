"""Daily post writer — after each midnight learning cycle, writes a
ready-to-post X/Twitter-style summary to posts/dayN_tweet.txt so it can
be published by hand. No API calls, no credentials — local files only.
"""

from __future__ import annotations

import os

DISCLAIMER = "AI simulation — not a real-world forecast."


def compose_post(log: dict) -> str:
    v = log.get("verdict", {})

    def s(key):
        a = v.get(key) or {}
        return f"{a['value']:.2f}" if a.get("value") is not None else "n/a"

    brent = (log.get("state_full") or {}).get("brent")
    brent_txt = f"${brent:.1f}" if brent else "n/a"
    sf = log.get("state_full") or {}
    pump = ""
    if sf.get("fr_petrol"):
        pump = (f"FR pump: petrol €{sf['fr_petrol']:.2f}/L · "
                f"diesel €{sf['fr_diesel']:.2f}/L"
                + (f" (rebate -€{sf['fr_fuel_rebate']:.2f})"
                   if sf.get("fr_fuel_rebate", 0) > 0.01 else ""))
    # pick the day's most influential agent's prediction as the key call
    learning = log.get("learning", {})
    influence = log.get("influence", {})
    key_event = ""
    if learning:
        ids = sorted(learning, key=lambda a: influence.get(a, 0),
                     reverse=True)
        for aid in ids + list(learning):
            p = (learning.get(aid) or {}).get("prediction")
            if p:
                key_event = p
                break
    key_event = key_event[:110] + ("…" if len(key_event) > 110 else "")

    date = log.get("date_range", "")
    day = (log.get("state_full", {}).get("round_no") or 1) - 1
    lines = [
        f"IRAN–US–ISR SIM · day {day} ({date})",
        f"P(war 72h) {s('p_war_72h')} · P(deal 7d) {s('p_deal_7d')} "
        f"· P(collapse) {s('p_collapse')}",
        f"Brent {brent_txt}",
    ]
    if pump:
        lines.append(pump)
    if key_event:
        lines.append(f"Key call: {key_event}")
    board = log.get("scoreboard") or {}
    if board:
        best = max(board, key=lambda a: board[a]["accuracy"])
        total = sum(b["n"] for b in board.values())
        lines.append(f"Ledger: {total} calls graded · top forecaster "
                     f"{best} ({board[best]['accuracy']:.0%} acc)")
    lines.append(DISCLAIMER)
    text = "\n".join(lines)
    return text[:278] if len(text) > 278 else text


def save_daily_post(log: dict, round_no: int,
                    out_dir: str = "posts") -> str:
    """Write posts/dayN_tweet.txt: the post text plus a reminder of which
    image to attach. Returns the file path."""
    os.makedirs(out_dir, exist_ok=True)
    image = f"media/day{round_no}_predictions.png"
    path = os.path.join(out_dir, f"day{round_no}_tweet.txt")
    with open(path, "w") as f:
        f.write(compose_post(log) + "\n\n")
        f.write(f"[attach image: {image}]\n")
    return path
