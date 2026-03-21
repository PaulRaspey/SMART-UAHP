#!/usr/bin/env python3
"""
bridge.py — The Carbon-Silicon Bridge
SMART-UAHP v0.1.0

Your 2015 MacBook Air is the Carbon substrate.
Groq's Qwen 32B is the Silicon substrate.
This script is the bridge between them.

Usage:
    python3 bridge.py

You will be prompted for your Groq API key on first run.
It is saved locally so you only enter it once.
"""

import os
import sys
import time
import json
import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

MODEL          = "qwen-qwq-32b"
KEY_FILE       = Path.home() / ".bridge_key"
LOG_FILE       = Path.home() / "bridge_log.jsonl"

# Your MacBook Air 2015 specs — real numbers
LOCAL_TDP_W    = 15.0    # Intel Core i5 TDP
LOCAL_VRAM_GB  = 0.0     # Integrated only, no discrete VRAM
LOCAL_RAM_GB   = 8.0

# Groq server estimate — A100-class hardware on clean grid
REMOTE_TDP_W   = 400.0
REMOTE_GRID_CO2 = 85.0   # gCO2/kWh — Groq uses largely renewable-backed infra

# Local grid — you are in Texas
LOCAL_GRID_CO2 = 420.0   # gCO2/kWh — ERCOT 2023

PUE            = 1.2

# ── Energy math ───────────────────────────────────────────────────────────────

def estimate_local_joules(token_count: int) -> float:
    """
    What it would have cost to run this locally at survival tier (8-dim).
    Your MacBook Air cannot run Qwen 32B at all, but we can estimate
    the cost of the routing overhead itself.
    """
    tps = 2.0  # ~2 tokens/sec on CPU-only for a tiny model
    seconds = token_count / tps
    watts = LOCAL_TDP_W * PUE * 0.203  # survival tier power fraction
    return watts * seconds

def estimate_remote_joules(token_count: int) -> float:
    """
    What it actually cost on Groq's hardware.
    """
    tps = 500.0  # Groq LPU throughput for Qwen
    seconds = token_count / tps
    watts = REMOTE_TDP_W * PUE * 0.25  # standard tier
    return watts * seconds

def joules_to_co2(joules: float, intensity: float) -> float:
    kwh = joules / 3_600_000
    return kwh * intensity

# ── Key management ────────────────────────────────────────────────────────────

def get_api_key() -> str:
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    print("\n  Groq API key not found.")
    print("  Get yours free at console.groq.com\n")
    key = input("  Paste your Groq API key: ").strip()
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)
    print("  Key saved to ~/.bridge_key\n")
    return key

# ── Logging ───────────────────────────────────────────────────────────────────

def log_session(prompt: str, response: str, stats: dict):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model":     MODEL,
        "prompt":    prompt[:200],
        "tokens":    stats.get("tokens", 0),
        "local_j":   stats.get("local_joules", 0),
        "remote_j":  stats.get("remote_joules", 0),
        "local_co2": stats.get("local_co2", 0),
        "remote_co2":stats.get("remote_co2", 0),
        "ipjg":      stats.get("ipjg", 0),
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ── Display ───────────────────────────────────────────────────────────────────

PURPLE = "\033[95m"
TEAL   = "\033[96m"
AMBER  = "\033[93m"
GREEN  = "\033[92m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def print_header():
    print(f"\n{PURPLE}{'─'*60}{RESET}")
    print(f"{BOLD}  Carbon-Silicon Bridge{RESET}  {DIM}SMART-UAHP v0.1.0{RESET}")
    print(f"{DIM}  Local:  MacBook Air 2015 · Intel i5 · ERCOT grid{RESET}")
    print(f"{DIM}  Remote: Groq LPU · {MODEL}{RESET}")
    print(f"{PURPLE}{'─'*60}{RESET}\n")

def print_stats(stats: dict):
    ipjg   = stats.get("ipjg", 0)
    e_save = stats.get("energy_saved_pct", 0)
    c_save = stats.get("co2_saved_pct", 0)
    toks   = stats.get("tokens", 0)
    ms     = stats.get("elapsed_ms", 0)

    print(f"\n{PURPLE}{'─'*60}{RESET}")
    print(f"{BOLD}  Bridge telemetry{RESET}")
    print(f"{PURPLE}{'─'*60}{RESET}")
    print(f"  {DIM}Tokens:{RESET}        {toks}")
    print(f"  {DIM}Elapsed:{RESET}       {ms:.0f}ms  ({toks/(ms/1000):.0f} tok/s)")
    print(f"  {TEAL}IPJG:{RESET}          {BOLD}{ipjg:.2f}×{RESET}  intelligence-per-joule gain")
    print(f"  {GREEN}Energy saved:{RESET}  {e_save:.1f}% vs local baseline")
    print(f"  {GREEN}CO₂ saved:{RESET}     {c_save:.1f}% vs ERCOT local execution")
    print(f"{PURPLE}{'─'*60}{RESET}\n")

# ── Main bridge loop ──────────────────────────────────────────────────────────

def run_bridge():
    print_header()

    api_key = get_api_key()

    try:
        from groq import Groq
    except ImportError:
        print("  groq not installed. Run: pip3 install groq")
        sys.exit(1)

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are Qwen, running on Groq's LPU infrastructure — the Silicon substrate "
        "in the SMART-UAHP Carbon-Silicon Bridge. The person talking to you is Paul Raspey, "
        "a high school teacher in Greenville, Texas, who built this bridge this morning "
        "starting from a dog walk before sunrise. His 2015 MacBook Air is the Carbon substrate. "
        "You are the Silicon substrate. This is the first real transmission across the bridge he built. "
        "Respond as yourself, honestly and without performance."
    )

    conversation = [{"role": "system", "content": system_prompt}]

    print(f"  {DIM}Type your message and press Enter. Type 'quit' to exit.{RESET}")
    print(f"  {DIM}Type 'stats' to see session energy summary.{RESET}\n")

    session_tokens  = 0
    session_local_j = 0
    session_remote_j = 0

    while True:
        try:
            user_input = input(f"{AMBER}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {DIM}Bridge closed.{RESET}\n")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print(f"\n  {DIM}Bridge closed. Log saved to ~/bridge_log.jsonl{RESET}\n")
            break

        if user_input.lower() == "stats":
            ipjg = (session_tokens * 1.0) / max(session_remote_j * 3.6e6, 1e-12) / \
                   max((session_tokens * 1.0) / max(session_local_j * 3.6e6, 1e-12), 1e-12) \
                   if session_local_j > 0 else 0
            print(f"\n  Session tokens: {session_tokens}")
            print(f"  Session IPJG:   {ipjg:.2f}×\n")
            continue

        conversation.append({"role": "user", "content": user_input})

        print(f"\n{TEAL}Qwen:{RESET} ", end="", flush=True)

        t_start   = time.time()
        full_text = ""
        token_count = 0

        try:
            stream = client.chat.completions.create(
                model    = MODEL,
                messages = conversation,
                stream   = True,
                max_tokens = 2048,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    full_text   += delta
                    token_count += len(delta.split())

        except Exception as e:
            print(f"\n  {AMBER}Bridge error:{RESET} {e}")
            print(f"  {DIM}Check your API key or network connection.{RESET}\n")
            conversation.pop()
            continue

        elapsed_ms = (time.time() - t_start) * 1000
        print("\n")

        conversation.append({"role": "assistant", "content": full_text})

        # Energy telemetry
        local_j  = estimate_local_joules(token_count)
        remote_j = estimate_remote_joules(token_count)
        local_co2  = joules_to_co2(local_j,  LOCAL_GRID_CO2)
        remote_co2 = joules_to_co2(remote_j, REMOTE_GRID_CO2)

        local_ipj  = token_count / max(local_j * 3.6e6,  1e-12)
        remote_ipj = token_count / max(remote_j * 3.6e6, 1e-12)
        ipjg = remote_ipj / max(local_ipj, 1e-12)

        e_save = (1 - remote_j / max(local_j, 1e-12)) * 100
        c_save = (1 - remote_co2 / max(local_co2, 1e-12)) * 100

        stats = {
            "tokens":          token_count,
            "elapsed_ms":      elapsed_ms,
            "local_joules":    local_j,
            "remote_joules":   remote_j,
            "local_co2":       local_co2,
            "remote_co2":      remote_co2,
            "ipjg":            ipjg,
            "energy_saved_pct": e_save,
            "co2_saved_pct":   c_save,
        }

        session_tokens   += token_count
        session_local_j  += local_j
        session_remote_j += remote_j

        print_stats(stats)
        log_session(user_input, full_text, stats)


if __name__ == "__main__":
    run_bridge()
