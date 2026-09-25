"""Round visualization — animated GIF + static PNG built from the
per-action snapshots the Director records.

Frames = one per snapshot (round start, each agent's act, round close)
plus a few hold frames so the viewer can read the final state and Jev's
typed scores. Pure matplotlib, Agg backend — no display needed.
"""

from __future__ import annotations

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
    date_range = log.get("state_full", {}).get("date_range", "")
    prefix = prefix or f"round{round_no}"
    gif_path = f"{prefix}_animation.gif"
    png_path = f"{prefix}_summary.png"
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
