"""Nightly daemon — keeps the simulation resident and runs one full
simulated day at every 00:00 local time, forever.

Each midnight run:
  1. plays the day (Jev-driven acting order, gated escalation),
  2. runs the midnight learning cycle (agents review real outcomes,
     update beliefs, file predictions),
  3. saves all graphs (animation, summary, learning board, focused
     predictions, before/after learning, cumulative history),
  4. appends the day to the dump file (which doubles as the resume
     checkpoint), then sleeps until the next midnight.

Run detached, e.g.:
    nohup python3 main.py --daemon --dump sim_log.json > daemon.out 2>&1 &
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timedelta

from .director import Director, _load_resume, _p, BAR

_running = True


def _stop(signum, frame):
    global _running
    _running = False
    _p(f"\n[{_ts()}] shutdown signal received — finishing cleanly")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _seconds_until_midnight() -> float:
    now = datetime.now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0,
                                           second=0, microsecond=0)
    return (nxt - now).total_seconds()


def _sleep_until_midnight() -> None:
    """Sleep in 30s slices so SIGTERM is honoured promptly."""
    while _running:
        remaining = _seconds_until_midnight()
        if remaining <= 1:
            return
        time.sleep(min(30.0, remaining))


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
               viz: bool, learn: bool, run_now: bool) -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

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

    _p(BAR)
    _p(f"[{_ts()}] SIMULATION DAEMON ONLINE — one day runs at every 00:00")
    _p(f"[{_ts()}] checkpoint/log file: {dump_path}")
    _p(BAR)

    first = run_now
    while _running:
        if first:
            _p(f"[{_ts()}] --run-now: executing a day immediately")
        else:
            wait = _seconds_until_midnight()
            _p(f"[{_ts()}] waiting for midnight "
               f"({wait / 3600:.1f}h until next cycle)...")
            _sleep_until_midnight()
            if not _running:
                break
        first = False

        _p(f"\n{BAR}\n[{_ts()}] === NEW SIMULATION DAY "
           f"{d.state.round_no} STARTS ===\n{BAR}")
        try:
            entry = d.run_round()
        except Exception as exc:
            _p(f"[{_ts()}] !! day {d.state.round_no} crashed: {exc} "
               f"— checkpoint preserved, retrying next midnight")
            continue
        append_dump(dump_path, entry)
        _p(f"\n[{_ts()}] DAY {d.state.round_no - 1} COMPLETE — "
           f"graphs + checkpoint saved")
        _p(f"[{_ts()}]   -> {dump_path} now holds "
           f"{len(d.history)} simulated days")

    _p(f"[{_ts()}] daemon stopped. Checkpoint in {dump_path}")
