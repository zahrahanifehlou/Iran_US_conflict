"""Round visualization — animated GIF + static PNG built from the
per-action snapshots the Director records.

Frames = one per snapshot (round start, each agent's act, round close)
plus a few hold frames so the viewer can read the final state and Jev's
typed scores. Pure matplotlib, Agg backend — no display needed.
"""

from __future__ import annotations

import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

C_BRENT = "#e8743b"
C_WAR = "#c0392b"
C_PROT = "#f1c40f"
C_COH = "#8e44ad"
C_GAS = "#2980b9"
C_SUP = "#16a085"
HOLD_FRAMES = 7          # extra frames on the final state
FPS = 1.5
OUT_DIR = "media"        # all PNG/GIF artifacts land here


def _out(name: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    return os.path.join(OUT_DIR, name)


def _jev_footer(verdict: dict) -> str:
    def s(key):
        a = verdict.get(key)
        return "n/a" if not a else f"{a['value']:.2f}"
    fc = verdict.get("forecast_7_14d", {})

    def f(key):
        a = fc.get(key)
        return "n/a" if not a else f"{a['value']:.2f}"
    return (f"JEV 72h/7d:  war {s('p_war_72h')}   deal {s('p_deal_7d')}   "
            f"collapse {s('p_collapse')}"
            f"      |      JEV 7-14d:  war {f('war_escalation_14d')}   "
            f"deal {f('deal_or_ceasefire_14d')}   "
            f"collapse {f('iran_econ_collapse_14d')}   "
            f"political shift {f('political_shift_14d')}")


def _setup_fig(round_no: int, date_range: str):
    fig = plt.figure(figsize=(14, 8.5))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.28],
                          hspace=0.42, wspace=0.28,
                          left=0.06, right=0.97, top=0.90, bottom=0.10)
    axes = {
        "brent": fig.add_subplot(gs[0, 0]),
        "war": fig.add_subplot(gs[0, 1]),
        "ir": fig.add_subplot(gs[1, 0]),
        "us": fig.add_subplot(gs[1, 1]),
        "ev": fig.add_subplot(gs[2, :]),
    }
    axes["ev"].axis("off")
    fig.suptitle(f"ROUND {round_no} — Iran · US · Israel — {date_range}",
                 fontsize=15, fontweight="bold")
    return fig, axes


def _draw_into(axes, snaps, k, verdict, end: bool):
    """Paint snapshot steps 0..k into the four panels + event ticker."""
    xs = list(range(len(snaps)))
    labels = [s["label"] for s in snaps]
    cur = snaps[k]

    def series(key):
        return [s[key] for s in snaps]

    ax_brent, ax_war, ax_ir, ax_us, ax_ev = (
        axes["brent"], axes["war"], axes["ir"], axes["us"], axes["ev"])
    for ax in (ax_brent, ax_war, ax_ir, ax_us):
        ax.clear()
    ax_ev.clear(); ax_ev.axis("off")

    # ---- Brent ----------------------------------------------------
    ax_brent.plot(xs[:k + 1], series("brent")[:k + 1],
                  color=C_BRENT, lw=2.4, marker="o", ms=5, zorder=3)
    ax_brent.axhline(100, color="#999", lw=0.8, ls=":")
    ax_brent.set_title("Brent crude ($/bbl)", loc="left", fontsize=11,
                       fontweight="bold")
    ax_brent.set_xticks(xs); ax_brent.set_xticklabels(
        labels, rotation=35, ha="right", fontsize=7.5)
    ax_brent.set_ylim(min(series("brent")) - 4, max(series("brent")) + 6)
    ax_brent.grid(alpha=0.25)
    ax_brent.annotate(f"${cur['brent']:.1f}", (k, cur["brent"]),
                      textcoords="offset points", xytext=(8, 8),
                      fontsize=10, fontweight="bold", color=C_BRENT)

    # ---- War intensity --------------------------------------------
    ax_war.plot(xs[:k + 1], series("war")[:k + 1],
                color=C_WAR, lw=2.4, marker="s", ms=5, zorder=3)
    for i, s in enumerate(snaps[:k + 1]):
        if s["esc_denied"]:
            ax_war.plot(i, s["war"], marker="X", ms=12, color="black",
                        zorder=4)
        elif s["review"]:
            ax_war.plot(i, s["war"], marker="*", ms=13, color="orange",
                        zorder=4)
    ax_war.set_ylim(0, 10.5)
    ax_war.set_title(f"War intensity /10   (Hormuz: "
                     f"{cur['hormuz'].replace('_', ' ')})",
                     loc="left", fontsize=11, fontweight="bold")
    ax_war.set_xticks(xs); ax_war.set_xticklabels(
        labels, rotation=35, ha="right", fontsize=7.5)
    ax_war.grid(alpha=0.25)
    ax_war.annotate("X = Jev denied escalation   * = human review",
                    (0.02, 0.04), xycoords="axes fraction", fontsize=7.5,
                    color="#555")

    # ---- Iran street ----------------------------------------------
    ax_ir.plot(xs[:k + 1], series("protests")[:k + 1],
               color=C_PROT, lw=2.2, marker="o", ms=5,
               label="protests /10")
    ax_ir.plot(xs[:k + 1], [c * 10 for c in series("cohesion")[:k + 1]],
               color=C_COH, lw=2.2, marker="d", ms=5,
               label="regime cohesion x10")
    ax_ir.plot(xs[:k + 1], series("econ_pressure")[:k + 1],
               color="#7f8c8d", lw=1.4, ls="--",
               label="econ pressure /10")
    ax_ir.set_ylim(0, 10.5)
    ax_ir.set_title("Iran street & regime", loc="left", fontsize=11,
                    fontweight="bold")
    ax_ir.legend(fontsize=7.5, loc="upper left", framealpha=0.8)
    ax_ir.set_xticks(xs); ax_ir.set_xticklabels(
        labels, rotation=35, ha="right", fontsize=7.5)
    ax_ir.grid(alpha=0.25)

    # ---- US domestic ----------------------------------------------
    ax_us.plot(xs[:k + 1], series("gas")[:k + 1],
               color=C_GAS, lw=2.4, marker="o", ms=5, label="gas $/gal")
    lo, hi = min(series("gas")), max(series("gas"))
    ax_us.set_ylim(lo - 0.3, hi + 0.3 if hi > lo else hi + 0.6)
    ax_us.set_title("US domestic", loc="left", fontsize=11,
                    fontweight="bold")
    ax_us.set_ylabel("gas $/gal", color=C_GAS)
    ax_us.tick_params(axis="y", labelcolor=C_GAS)
    ax_us.set_xticks(xs); ax_us.set_xticklabels(
        labels, rotation=35, ha="right", fontsize=7.5)
    ax_us.grid(alpha=0.25)
    ax2 = ax_us.twinx()
    ax2.plot(xs[:k + 1], series("war_support")[:k + 1],
             color=C_SUP, lw=1.8, ls="--", marker="v", ms=4,
             label="war support")
    ax2.set_ylim(0, 1); ax2.set_ylabel("war support", color=C_SUP)
    ax2.tick_params(axis="y", labelcolor=C_SUP)

    # ---- event ticker ----------------------------------------------
    event = cur["event"]
    wrapped = "\n".join(textwrap.wrap(event, 118))
    color = "#c0392b" if cur.get("esc_denied") else "#222"
    ax_ev.text(0, 0.85, f"t={k}  {wrapped}", fontsize=9.5,
               va="top", color=color, fontfamily="monospace")
    if end:
        ax_ev.text(0, 0.30, _jev_footer(verdict), fontsize=9,
                   va="top", color="#0b5394", fontfamily="monospace",
                   fontweight="bold")


def render_round(log: dict, round_no: int,
                 prefix: str | None = None) -> tuple[str, str]:
    snaps = log["snapshots"]
    verdict = log["verdict"]
    date_range = log.get("date_range") or \
        log.get("state_full", {}).get("date_range", "")
    prefix = prefix or f"round{round_no}"
    gif_path = _out(f"{prefix}_animation.gif")
    png_path = _out(f"{prefix}_summary.png")
    n_frames = len(snaps) + HOLD_FRAMES

    # --- animated figure ---------------------------------------------
    fig, axes = _setup_fig(round_no, date_range)

    def draw(frame):
        k = min(frame, len(snaps) - 1)
        _draw_into(axes, snaps, k, verdict, end=frame >= len(snaps))
        return []

    anim = FuncAnimation(fig, draw, frames=n_frames,
                         interval=int(1000 / FPS), repeat=False)
    anim.save(gif_path, writer=PillowWriter(fps=FPS))
    plt.close(fig)

    # --- summary PNG on a separate figure (FuncAnimation hooks canvas
    #     draw events and would re-render frame 0 on savefig) ----------
    fig2, axes2 = _setup_fig(round_no, date_range)
    _draw_into(axes2, snaps, len(snaps) - 1, verdict, end=True)
    fig2.savefig(png_path, dpi=110)
    plt.close(fig2)

    return gif_path, png_path


# ==================================================================
#  Daily learning chart — what each agent concluded at midnight
# ==================================================================
_STANCE_COLORS = {
    "hawk": "#c0392b", "escalat": "#c0392b", "aggress": "#c0392b",
    "dov": "#16a085", "caut": "#2980b9", "patient": "#2980b9",
    "desper": "#e67e22", "opportun": "#8e44ad",
}


def _stance_color(stance: str) -> str:
    s = (stance or "").lower()
    for k, c in _STANCE_COLORS.items():
        if k in s:
            return c
    return "#555"


def render_learning(log: dict, round_no: int,
                    prefix: str | None = None) -> str:
    learning = log.get("learning", {})
    influence = log.get("influence", {})
    prefix = prefix or f"day{round_no}"
    path = _out(f"{prefix}_learning.png")

    fig = plt.figure(figsize=(15, 13))
    gs = fig.add_gridspec(1, 2, width_ratios=[2.4, 1], left=0.02,
                          right=0.98, top=0.94, bottom=0.02, wspace=0.12)
    ax = fig.add_subplot(gs[0, 0]); ax.axis("off")
    ax_inf = fig.add_subplot(gs[0, 1])

    fig.suptitle(f"MIDNIGHT LEARNING — day {round_no} "
                 f"({log.get('date_range', '')})",
                 fontsize=15, fontweight="bold")

    ids = [a for a in learning if learning[a].get("learned")]
    n = max(len(ids), 1)
    row = 1.0 / n
    for i, aid in enumerate(ids):
        y = 1 - i * row
        l = learning[aid]
        sc = l.get("scorecard", {})
        col = _stance_color(l.get("stance"))
        ax.text(0.0, y - 0.008, l.get("name", aid).upper(),
                fontsize=10, fontweight="bold", color=col,
                transform=ax.transAxes)
        learned = textwrap.shorten(l.get("learned", "—"), 210,
                                   placeholder="…")
        ax.text(0.0, y - 0.030,
                textwrap.fill(f"learned: {learned}", 92),
                fontsize=8, va="top", transform=ax.transAxes, color="#222")
        pred = textwrap.shorten(l.get("prediction", "—"), 190,
                                placeholder="…")
        ax.text(0.0, y - 0.066,
                textwrap.fill(
                    f"predicts: {pred} "
                    f"[war {l.get('p_war','?')}/10 · deal "
                    f"{l.get('p_deal','?')}/10 · brent "
                    f"{l.get('brent_dir','?')}]  "
                    f"score {sc.get('hits',0)}W-{sc.get('misses',0)}L", 92),
                fontsize=8, va="top", transform=ax.transAxes,
                color="#0b5394")

    # ---- influence bars ----------------------------------------------
    inf_ids = sorted(influence, key=influence.get, reverse=True)
    ax_inf.barh([SHORT_LABELS.get(i, i) for i in inf_ids][::-1],
                [influence[i] for i in inf_ids][::-1],
                color="#c0392b", alpha=0.8)
    ax_inf.set_title("Influence on the world state (today)",
                     fontsize=10, fontweight="bold")
    ax_inf.tick_params(labelsize=8)
    ax_inf.grid(axis="x", alpha=0.25)

    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


SHORT_LABELS = {
    "trump": "US", "netanyahu": "Israel", "iran_hardliners": "Iran",
    "russia": "Russia", "china": "China", "eu": "EU",
    "taiwan": "Taiwan", "gulf": "Gulf", "turkey": "Turkey",
    "oil_market": "Oil", "gas_market": "Gas", "shipping": "Shipping",
    "markets": "Markets", "central_banks": "CenBanks",
    "us_public": "US pub", "iran_public": "IR pub",
    "israeli_public": "IL pub", "media": "Media",
    "humanitarian": "Humanit.",
}


# ==================================================================
#  Cumulative history — updated after every day
# ==================================================================
def render_history(history: list[dict],
                   path: str = "sim_history.png") -> str:
    path = _out(path)
    if not history:
        return path
    days = [h["day"] for h in history]
    xlabels = [f"d{h['day']}" for h in history]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    fig.suptitle("SIMULATION HISTORY — day by day", fontsize=15,
                 fontweight="bold")

    # oil --------------------------------------------------------------
    ax = axes[0]
    ax.plot(days, [h["brent"] for h in history], color=C_BRENT, lw=2.4,
            marker="o", label="Brent $/bbl")
    if any(h.get("wti") for h in history):
        ax.plot(days, [h.get("wti") or 0 for h in history],
                color="#e8743b", lw=1.4, ls=":", alpha=0.7,
                label="WTI $/bbl")
        ax.legend(fontsize=8, loc="upper left")
    ax2 = ax.twinx()
    ax2.plot(days, [h["gas"] for h in history], color=C_GAS, lw=1.8,
             ls="--", marker="v", label="US gas $/gal")
    ax2.set_ylabel("gas $/gal", color=C_GAS)
    ax2.tick_params(axis="y", labelcolor=C_GAS)
    for h, x in zip(history, days):
        if h.get("hormuz") not in ("open", "threatened"):
            ax.axvspan(x - 0.4, x + 0.4, color="#c0392b", alpha=0.10)
    ax.set_ylabel("Brent $/bbl", color=C_BRENT)
    ax.tick_params(axis="y", labelcolor=C_BRENT)
    ax.set_title("Oil & gas (shaded = Hormuz constrained)", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(alpha=0.25)

    # jev probabilities -------------------------------------------------
    ax = axes[1]
    for key, color, name in (("p_war_72h", C_WAR, "P war 72h"),
                             ("p_deal_7d", C_SUP, "P deal 7d"),
                             ("p_collapse", "#e67e22", "P collapse")):
        vals = [h.get(key) for h in history]
        xs = [d for d, v in zip(days, vals) if v is not None]
        ys = [v for v in vals if v is not None]
        if xs:
            ax.plot(xs, ys, color=color, lw=2, marker="o", label=name)
    ax.set_ylim(0, 1.02)
    ax.set_title("Jev probability track", loc="left", fontsize=11,
                 fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25)

    # cumulative influence ----------------------------------------------
    ax = axes[2]
    totals: dict[str, float] = {}
    for h in history:
        for aid, v in (h.get("influence") or {}).items():
            totals[aid] = totals.get(aid, 0) + v
    ids = sorted(totals, key=totals.get, reverse=True)
    ax.bar([SHORT_LABELS.get(i, i) for i in ids],
           [totals[i] for i in ids], color="#2c3e50", alpha=0.85)
    ax.set_title("Cumulative agent influence", loc="left", fontsize=11,
                 fontweight="bold")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.25)

    for a in axes[:2]:
        a.set_xticks(days)
        a.set_xticklabels(xlabels)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


# ==================================================================
#  Prediction scoreboard — accuracy, Brier, calibration, by horizon
# ==================================================================
def render_scoreboard(scoreboard: dict,
                      path: str = "prediction_scoreboard.png") -> str:
    """Cumulative prediction-quality board across all resolved calls."""
    path = _out(path)
    scored = {a: s for a, s in scoreboard.items() if s.get("n")}
    if not scored:
        return path

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("PREDICTION SCOREBOARD — every graded call, cumulative",
                 fontsize=15, fontweight="bold")
    ids = sorted(scored, key=lambda a: scored[a]["accuracy"],
                 reverse=True)
    names = [SHORT_LABELS.get(i, i) for i in ids]

    # accuracy ------------------------------------------------------------
    ax = axes[0][0]
    ax.barh(names[::-1],
            [scored[i]["accuracy"] * 100 for i in ids][::-1],
            color=C_SUP, alpha=0.85)
    for y, i in enumerate(ids[::-1]):
        ax.text(scored[i]["accuracy"] * 100 + 1, y,
                f"{scored[i]['n']} calls", va="center", fontsize=8)
    ax.set_xlim(0, 115)
    ax.set_title("Accuracy % (bar) · n resolved calls", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)

    # brier ----------------------------------------------------------------
    ax = axes[0][1]
    ax.barh(names[::-1], [scored[i]["brier"] for i in ids][::-1],
            color=C_WAR, alpha=0.85)
    ax.axvline(0.25, color="#555", ls="--", lw=1)
    ax.text(0.255, -0.4, "coin-flip 0.25", fontsize=8, color="#555")
    ax.set_title("Mean Brier score (lower is better)", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)

    # calibration curve ----------------------------------------------------
    ax = axes[1][0]
    bins = {}
    for s in scored.values():
        for bidx, cb in (s.get("conf_bins") or {}).items():
            t = bins.setdefault(bidx, {"n": 0, "conf": 0.0, "freq": 0.0})
            t["n"] += cb["n"]; t["conf"] += cb["conf"]; t["freq"] += cb["freq"]
    xs = [t["conf"] / t["n"] for _, t in sorted(bins.items()) if t["n"]]
    ys = [t["freq"] / t["n"] for _, t in sorted(bins.items()) if t["n"]]
    ns = [t["n"] for _, t in sorted(bins.items()) if t["n"]]
    ax.plot([0, 1], [0, 1], color="#555", ls="--", lw=1)
    if xs:
        ax.scatter(xs, ys, s=[max(30, n * 8) for n in ns],
                   color=C_BRENT, alpha=0.8, zorder=3)
        ax.plot(xs, ys, color=C_BRENT, lw=1.6)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("stated confidence"); ax.set_ylabel("empirical frequency")
    ax.set_title("Calibration — does 70% mean 70%?", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(alpha=0.25)

    # accuracy by horizon ---------------------------------------------------
    ax = axes[1][1]
    horizons = ["24h", "72h", "7d", "14d", "30d"]
    accs, counts = [], []
    for h in horizons:
        n = sum((s.get("by_horizon", {}).get(h) or {}).get("n", 0)
                for s in scored.values())
        a = [s["by_horizon"][h]["acc"] for s in scored.values()
             if s.get("by_horizon", {}).get(h)]
        accs.append(sum(a) / len(a) if a else 0)
        counts.append(n)
    ax.bar(horizons, [a * 100 for a in accs], color=C_GAS, alpha=0.85)
    for x, (a, n) in enumerate(zip(accs, counts)):
        if n:
            ax.text(x, a * 100 + 1, f"n={n}", ha="center", fontsize=8)
    ax.set_ylim(0, 115)
    ax.set_title("Accuracy by horizon (all agents)", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(axis="y", alpha=0.25)

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
    return path


# ==================================================================
#  Focused predictions — what every agent expects tomorrow
# ==================================================================
def render_predictions(log: dict, round_no: int,
                       prefix: str | None = None) -> tuple[str, str]:
    """Two charts:
    dayN_predictions.png  — per-agent P_war / P_deal for tomorrow +
                            their predicted event + brent call.
    dayN_before_after.png — dumbbells: each agent's P_war / P_deal
                            BEFORE the day (last night's call) vs AFTER
                            tonight's learning.
    """
    learning = log.get("learning", {})
    verdict = log.get("verdict", {})
    prefix = prefix or f"day{round_no}"
    p_path = _out(f"{prefix}_predictions.png")
    b_path = _out(f"{prefix}_before_after.png")

    ids = [a for a in learning if learning[a].get("prediction")]
    names = [SHORT_LABELS.get(i, i) for i in ids]
    pw = [learning[i].get("p_war") or 0 for i in ids]
    pd_ = [learning[i].get("p_deal") or 0 for i in ids]

    # ---- focused predictions ------------------------------------------
    fig, (axp, axt) = plt.subplots(
        1, 2, figsize=(15, 6 + 0.55 * len(ids)),
        gridspec_kw={"width_ratios": [1.15, 1.6]})
    y = list(range(len(ids)))
    axp.barh([i - 0.18 for i in y], pw, height=0.36,
             color=C_WAR, label="P(war tomorrow)")
    axp.barh([i + 0.18 for i in y], pd_, height=0.36,
             color=C_SUP, label="P(deal tomorrow)")
    for i, a in enumerate(ids):
        d = (learning[a].get("brent_dir") or "").lower()
        mark = {"up": "▲", "down": "▼", "flat": "■"}.get(d, "?")
        axp.text(10.4, i, mark, va="center", fontsize=11,
                 color={"up": "#c0392b", "down": "#16a085"}.get(d, "#555"))
    jw = (verdict.get("p_war_72h") or {}).get("value")
    jd = (verdict.get("p_deal_7d") or {}).get("value")
    if jw is not None:
        axp.axvline(jw * 10, color=C_WAR, ls=":", lw=1.4)
        axp.text(jw * 10 + 0.08, len(ids) - 0.4, f"Jev war {jw:.2f}",
                 fontsize=7.5, color=C_WAR)
    if jd is not None:
        axp.axvline(jd * 10, color=C_SUP, ls=":", lw=1.4)
        axp.text(jd * 10 + 0.08, -0.6, f"Jev deal {jd:.2f}",
                 fontsize=7.5, color=C_SUP)
    axp.set_yticks(y); axp.set_yticklabels(names, fontsize=9)
    axp.set_xlim(0, 11.6); axp.invert_yaxis()
    axp.set_title("P(outcome tomorrow), /10   (right edge = Brent call)",
                  loc="left", fontsize=11, fontweight="bold")
    axp.legend(fontsize=8, loc="lower right"); axp.grid(axis="x", alpha=.25)

    axt.axis("off")
    axt.set_title("Predicted event for tomorrow", loc="left",
                  fontsize=11, fontweight="bold")
    for i, a in enumerate(ids):
        txt = textwrap.fill(learning[a]["prediction"], 70)
        axt.text(0, 1 - (i + 0.55) / max(len(ids), 1), txt,
                 fontsize=8.2, va="top", transform=axt.transAxes)
    fig.suptitle(f"FOCUSED PREDICTIONS — night of day {round_no} "
                 f"({log.get('date_range', '')})",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(p_path, dpi=110)
    plt.close(fig)

    # ---- before vs after learning --------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.7 * len(ids) + 2.2),
                             sharey=True)
    for ax, key, ttl, color in (
            (axes[0], "p_war", "P(war) — before vs after learning", C_WAR),
            (axes[1], "p_deal", "P(deal) — before vs after learning", C_SUP)):
        for i, a in enumerate(ids):
            prev = (learning[a].get("prev_prediction") or {}).get(key)
            new = learning[a].get(key)
            if prev is None and new is None:
                continue
            if prev is not None:
                ax.plot(prev, i, "o", ms=7, color="#bbb", zorder=3)
            if prev is not None and new is not None:
                ax.annotate("", xy=(new, i), xytext=(prev, i),
                            arrowprops=dict(arrowstyle="->", color=color,
                                            lw=2))
            if new is not None:
                ax.plot(new, i, "o", ms=8, color=color, zorder=4)
        ax.set_yticks(y); ax.set_yticklabels(names, fontsize=9)
        ax.set_xlim(-0.5, 10.5); ax.invert_yaxis()
        ax.set_title(ttl, loc="left", fontsize=10.5, fontweight="bold")
        ax.grid(axis="x", alpha=.25)
        ax.annotate("grey = last night's call · colored = after midnight "
                    "learning", (0, -0.14), xycoords="axes fraction",
                    fontsize=7.5, color="#555")
    fig.suptitle(f"BEFORE vs AFTER LEARNING — day {round_no}",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(b_path, dpi=110)
    plt.close(fig)

    return p_path, b_path
