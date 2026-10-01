"""The agent's brain: stages, prompts and tools. Transport-agnostic.

`tools.py` and `prompts.py` know nothing about Pipecat, so the same logic runs on a live
phone call (via `nodes.py`, the Pipecat Flows adapter) and in the text simulator (`sim/`).
"""
