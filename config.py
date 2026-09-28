"""Central configuration for the Iran-US-Israel multi-agent simulation.

All generation runs through a local Ollama instance. Nothing leaves the machine.

Model roles
-----------
JEV_MODEL    : fast "System 1" decision layer. Never writes prose — only typed
               choices, Noul (yes/no) answers and calibrated scores. A small
               model is correct here by design.
AGENT_MODEL  : default model for character agents (statements, strategy,
               in-character reasoning). Overridable per-agent in personas.py
               or globally via --fast / SIM_AGENT_MODEL.
"""

import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# --- decision layer ---------------------------------------------------------
JEV_MODEL = os.environ.get("SIM_JEV_MODEL", "llama3.2:3b")
JEV_TEMPERATURE = 0.1          # decisions should be near-deterministic
JEV_NUM_PREDICT = 96           # typed answers are tiny
JEV_RETRIES = 2                # re-ask on malformed JSON before fallback

# --- character agents -------------------------------------------------------
AGENT_MODEL = os.environ.get("SIM_AGENT_MODEL", "qwen35-uncensored:latest")
FAST_MODEL = os.environ.get("SIM_FAST_MODEL", "llama3.2:3b")
AGENT_NUM_PREDICT = 420        # statements stay punchy

# --- simulation -------------------------------------------------------------
SIM_TITLE = "Iran - US - Israel Conflict Simulation"
START_DATE = "25 September 2026"
REQUEST_TIMEOUT = 300          # seconds per Ollama call (big models are slow)

# --- social feed -------------------------------------------------------------
# provider: synthetic | real | bluesky | auto  (see simulation/xfeed.py)
#   real = free public X endpoints, fails loudly rather than fabricating
#   auto = real X first, then Bluesky public search (labelled, never hidden)
# Cached collections live in cache/xfeed/*.json — replay runs with no network.
X_FEED = {
    "provider": os.environ.get("SIM_FEED_PROVIDER", "synthetic"),
    "query": os.environ.get(
        "SIM_FEED_QUERY",
        "Iran OR Israel OR US OR Trump OR Hormuz OR Brent"),
    "max_posts": int(os.environ.get("SIM_FEED_MAX", "50")),
    "cache": os.environ.get("SIM_FEED_CACHE", "1") not in ("0", "false", "no"),
    "cache_ttl_hours": float(os.environ.get("SIM_FEED_TTL_H", "12")),
    "accounts": [h for h in os.environ.get(
        "SIM_FEED_ACCOUNTS",
        "realDonaldTrump,netanyahu,khamenei_ir,IranIntl_En,"
        "JavierBlas,amanpour,vonderleyen").split(",") if h],
    "nitter_instances": [h for h in os.environ.get(
        "SIM_FEED_NITTER",
        "nitter.net,nitter.privacydev.net").split(",") if h],
    "timeout": int(os.environ.get("SIM_FEED_TIMEOUT", "10")),
}

# --- swarm consensus layer ---------------------------------------------------
# A second forecasting voice next to Jev: the agents' midnight P_WAR/P_DEAL/
# BRENT_DIR votes, skill-weighted and iterated to a UNU-style consensus.
# Pure stdlib, no extra model calls. SIM_SWARM=0 disables.
SWARM = {
    "enabled": os.environ.get("SIM_SWARM", "1") not in ("0", "false", "no"),
    "pull": float(os.environ.get("SIM_SWARM_PULL", "0.35")),
    "iterations": int(os.environ.get("SIM_SWARM_ITERS", "12")),
    "epsilon": float(os.environ.get("SIM_SWARM_EPS", "0.0001")),
}
