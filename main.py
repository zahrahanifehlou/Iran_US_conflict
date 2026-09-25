#!/usr/bin/env python3
"""Iran - US - Israel conflict simulation. LLM agents + Jev decision layer.

Usage:
    python3 main.py                    # one round, full-size agent models
    python3 main.py --rounds 3         # several rounds (state carries forward)
    python3 main.py --resume run.json  # continue from a dumped world state
    python3 main.py --fast             # all agents on the small fast model
    python3 main.py --offline          # Jev heuristics only, no LLM calls
    python3 main.py --no-viz           # skip animation/PNG generation
    python3 main.py --dump run1.json   # save Jev verdicts + states to JSON
"""

import argparse
import sys

import ollama_client
from simulation.director import main as run


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--resume", metavar="FILE",
                    help="load last state_full from a --dump file and continue")
    ap.add_argument("--fast", action="store_true",
                    help="run every agent on the small fast model")
    ap.add_argument("--offline", action="store_true",
                    help="skip all Ollama calls (heuristic Jev, stub agents)")
    ap.add_argument("--no-viz", action="store_true",
                    help="do not render round animations")
    ap.add_argument("--no-learn", action="store_true",
                    help="skip the midnight learning cycle")
    ap.add_argument("--dump", metavar="FILE",
                    help="write round verdicts/state to JSON")
    args = ap.parse_args()

    if not args.offline and not ollama_client.ping():
        sys.exit("Ollama is not reachable at the configured host. "
                 "Start it, or run with --offline.")

    run(args.rounds, fast=args.fast, offline=args.offline, dump=args.dump,
        resume=args.resume, viz=not args.no_viz, learn=not args.no_learn)
