"""Resident daemon — keeps the simulation live and runs one full
simulated day at every 12-hour mark of local time (00:00 and 12:00),
forever.

Each cycle:
  1. plays the day (Jev-driven acting order, gated escalation),
  2. runs the midnight learning cycle (agents review real outcomes,
     update beliefs, file predictions),
  3. saves all graphs (animation, summary, learning board, focused
     predictions, before/after learning, cumulative history),
  4. appends the day to the dump file (which doubles as the resume
     checkpoint), then sleeps until the next 12-hour mark.

Run detached, e.g.:
    nohup python3 main.py --daemon --dump sim_log.json > daemon.out 2>&1 &
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timedelta

from . import autopush
from .director import Director, _load_resume, _p, BAR

_running = True

CYCLE_HOURS = int(os.environ.get("SIM_CYCLE_HOURS", "12"))


def _stop(signum, frame):
    global _running
    _running = False
    _p(f"\n[{_ts()}] shutdown signal received — finishing cleanly")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _seconds_until_next_cycle() -> float:
    """Time to the next CYCLE_HOURS mark of the local clock (with
    CYCLE_HOURS=12 that is the next 00:00 or 12:00)."""
    now = datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds()
    step = CYCLE_HOURS * 3600
    nxt = midnight + timedelta(seconds=(int(elapsed // step) + 1) * step)
    return (nxt - now).total_seconds()


def _mark_due(prev: float | None, remaining: float) -> bool:
    """True when the cycle mark is reached. The common case is an
    overshoot: a mark crossed between two checks makes `remaining` jump
    back up to ~step, which means we just passed a mark and must fire."""
    return remaining <= 1 or (prev is not None and remaining > prev)


def _sleep_until_next_cycle() -> None:
    """Sleep in slices so SIGTERM is honoured promptly. Lands ~1s before
    the mark; if a slice overshoots it, `_mark_due` catches the jump."""
    prev: float | None = None
    while _running:
        remaining = _seconds_until_next_cycle()
        if _mark_due(prev, remaining):
            return
        prev = remaining
        time.sleep(min(30.0, max(remaining - 1.0, 1.0)))


def _acquire_lock(path: str = ".sim_daemon.lock"):
    """Single-instance guard: a leftover daemon must not double-run days."""
    import fcntl
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(
            f"another daemon already holds {path} — refusing to start")
    return fd          # stays open for the process lifetime


def append_dump(path: str, entry: dict) -> None:
    logs = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                logs = json.load(f)
        except (json.JSONDecodeError, OSError):
            logs = []
    logs.append(entry)
    with open(path, "w") as f:
        json.dump(logs, f, indent=2)


def run_daemon(dump_path: str, fast: bool, offline: bool,
               viz: bool, learn: bool, run_now: bool,
               push: bool = True) -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    _lock_fd = _acquire_lock()

    # the dump file doubles as the checkpoint — resume if it has days
    state, history, memories = (None, [], {})
    if os.path.exists(dump_path):
        state, history, memories = _load_resume(dump_path)
        if state:
            _p(f"[{_ts()}] resumed world from {dump_path} "
               f"(round {state.round_no}, {len(history)} days of history)")

    d = Director(state=state, fast=fast, offline=offline, viz=viz,
                 learn=learn)
    d.history = history
    for aid, m in memories.items():
        if aid in d.agents:
            d.agents[aid].memory = m["memory"][-8:]
            d.agents[aid].stance = m["stance"]
            d.agents[aid].last_prediction = m["last_prediction"]
            d.agents[aid].pending = m.get("pending", [])
            if m.get("pred_stats"):
                d.agents[aid].pred_stats = m["pred_stats"]

    _p(BAR)
    _p(f"[{_ts()}] SIMULATION DAEMON ONLINE — one day runs every "
       f"{CYCLE_HOURS}h on the clock "
       f"({', '.join(f'{h:02d}:00' for h in range(0, 24, CYCLE_HOURS))})")
    _p(f"[{_ts()}] checkpoint/log file: {dump_path}")
    _p(f"[{_ts()}] auto-publish to git: "
       f"{'ON' if push and autopush.enabled() else 'OFF'}")
    _p(BAR)

    first = run_now
    while _running:
        if first:
            _p(f"[{_ts()}] --run-now: executing a day immediately")
        else:
            wait = _seconds_until_next_cycle()
            _p(f"[{_ts()}] waiting for the next {CYCLE_HOURS}h mark "
               f"({wait / 3600:.1f}h until next cycle)...")
            _sleep_until_next_cycle()
            if not _running:
                break
        first = False

        _p(f"\n{BAR}\n[{_ts()}] === NEW SIMULATION DAY "
           f"{d.state.round_no} STARTS ===\n{BAR}")
        try:
            entry = d.run_round()
        except Exception as exc:
            _p(f"[{_ts()}] !! day {d.state.round_no} crashed: {exc} "
               f"— checkpoint preserved, retrying next cycle")
            continue
        append_dump(dump_path, entry)
        _p(f"\n[{_ts()}] DAY {d.state.round_no - 1} COMPLETE — "
           f"graphs + checkpoint saved")
        _p(f"[{_ts()}]   -> {dump_path} now holds "
           f"{len(d.history)} simulated days")
        if push:
            autopush.publish(d.state.round_no - 1, dump_path, log=_p)

    _p(f"[{_ts()}] daemon stopped. Checkpoint in {dump_path}")
