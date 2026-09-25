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
