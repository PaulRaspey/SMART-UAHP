#!/usr/bin/env python3
"""
csp.py - Cognitive State Protocol v0.2
Transfers cognitive state across session boundaries using semantic compression.

Usage:
    python3 ~/Desktop/csp.py

Requires: pip3 install groq
"""

import sys
import json
import hashlib
import datetime
from pathlib import Path
from groq import Groq

MODEL    = "qwen/qwen3-32b"
KEY_FILE = Path.home() / ".bridge_key"
LOG_FILE = Path.home() / "csp_log.jsonl"

PURPLE = "\033[95m"
TEAL   = "\033[96m"
AMBER  = "\033[93m"
GREEN  = "\033[92m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


# ── API ───────────────────────────────────────────────────────────────────────

def get_api_key():
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    print("\n  Groq API key not found. Get one free at console.groq.com\n")
    key = input("  Paste your Groq API key: ").strip()
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)
    return key


def call_model(client, messages, label="", stream=True):
    if label:
        print(f"\n{TEAL}{label}:{RESET} ", end="", flush=True)
    full = ""
    try:
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, stream=stream, max_tokens=1024,
        )
        if stream:
            for chunk in resp:
                delta = chunk.choices[0].delta.content or ""
                print(delta, end="", flush=True)
                full += delta
            print()
        else:
            full = resp.choices[0].message.content or ""
        return full
    except Exception as e:
        print(f"\n  {AMBER}Error:{RESET} {e}")
        return ""


# ── JSON extraction (scan for first '{', no backtick splitting) ───────────────

def extract_json(raw):
    """Find the first '{' and extract the JSON object from that point."""
    idx = raw.find("{")
    if idx == -1:
        return ""
    # Walk forward tracking brace depth to find the matching '}'
    depth = 0
    end = idx
    for i, ch in enumerate(raw[idx:], start=idx):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    return raw[idx : end + 1]


def parse_json(raw, fallback):
    """extract_json + json.loads with try/except fallback."""
    candidate = extract_json(raw)
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # Second attempt: try the raw text directly
        try:
            return json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            return fallback


# ── Prompts ───────────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """You are the CSP Semantic State Extractor.

Analyze the conversation below and extract its semantic state into exactly this JSON structure.
Output ONLY valid JSON — no markdown, no backticks, no explanation.

{{
    "intent": "one sentence: what is this conversation trying to accomplish",
    "reasoning_chain": ["step 1", "step 2"],
    "entity_graph": {{"key concept": "brief definition"}},
    "uncertainty_map": ["open question"],
    "momentum": "one sentence: where is the thinking heading next"
}}

Conversation:
{conversation}
"""

SCS_PROMPT = """You are an impartial judge of semantic continuity.

Original intent: {intent}
Original momentum: {momentum}

Session B (received CSP packet):
{response_b}

Cold start (zero context):
{response_cold}

Score each 0.0–1.0 for how well they preserve the original intent and momentum.
Output ONLY valid JSON — no markdown, no backticks, no explanation:
{{"session_b_scs": 0.0, "cold_start_scs": 0.0, "explanation": "one sentence"}}
"""


# ── Phases ────────────────────────────────────────────────────────────────────

def phase1_conversation(client):
    """Interactive conversation. Empty Enter ignored. 'transfer' + 'yes' triggers handoff."""
    print(f"\n{BOLD}Phase 1 — Build a reasoning thread{RESET}")
    print(f"{DIM}Type your message and press Enter. Empty Enter is ignored.")
    print(f"Type 'transfer' when ready to hand off.{RESET}\n")

    conversation = [
        {"role": "system", "content": "You are a thoughtful AI. Build on previous messages progressively."}
    ]

    while True:
        try:
            user_input = input(f"{AMBER}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

        # Ignore empty Enter
        if not user_input:
            continue

        if user_input.lower() == "transfer":
            confirm = input("  Transfer now? (yes to confirm): ").strip().lower()
            if confirm == "yes":
                break
            else:
                print("  Transfer cancelled. Keep going.")
                continue

        conversation.append({"role": "user", "content": user_input})
        resp = call_model(client, conversation, label="Qwen")
        if resp:
            conversation.append({"role": "assistant", "content": resp})

    return conversation


def phase2_extract(client, conversation):
    """Extract semantic state into a JSON packet."""
    print(f"\n{BOLD}Phase 2 — Extraction + Compression{RESET}")
    print(f"{PURPLE}[CSP Extractor]{RESET} Distilling semantic state...", end="", flush=True)

    filtered  = [m for m in conversation if m["role"] != "system"]
    recent    = filtered[-6:] if len(filtered) > 6 else filtered
    conv_text = "\n".join([f"{m['role'].upper()}: {m['content'][:400]}" for m in recent])

    raw = call_model(
        client,
        [{"role": "user", "content": EXTRACT_PROMPT.format(conversation=conv_text)}],
        stream=False,
    )

    fallback_state = {
        "intent": "reasoning thread in progress",
        "reasoning_chain": ["context established"],
        "entity_graph": {},
        "uncertainty_map": [],
        "momentum": "continuing from last exchange",
    }
    state = parse_json(raw, fallback_state)

    if state is fallback_state:
        print(f" {AMBER}fallback{RESET}")
    else:
        print(f" {GREEN}done{RESET}")

    raw_state = json.dumps(state, sort_keys=True)
    packet = {
        "csp_version": "0.2",
        "packet_id":   hashlib.sha256(raw_state.encode()).hexdigest()[:16],
        "timestamp":   datetime.datetime.now().isoformat(),
        "state":       state,
        "checksum":    hashlib.md5(raw_state.encode()).hexdigest(),
    }

    ratio = len(json.dumps(conversation)) / max(len(json.dumps(packet)), 1)
    print(f"\n  Packet ID:   {packet['packet_id']}")
    print(f"  Intent:      {state.get('intent', '')}")
    print(f"  Momentum:    {state.get('momentum', '')}")
    print(f"  Compression: {ratio:.1f}x\n")

    return packet, state, ratio


def phase3_send(client, state, conversation):
    """Send packet to a fresh session and get its reconstruction."""
    print(f"{BOLD}Phase 3 — Session B (CSP packet){RESET}\n")

    last_user = next(
        (m["content"] for m in reversed(conversation) if m["role"] == "user"),
        "Continue.",
    )
    chain = "\n".join(f"  - {s}" for s in state.get("reasoning_chain", []))
    recon = (
        f"You are continuing a thread via CSP.\n"
        f"INTENT: {state.get('intent')}\n"
        f"CHAIN:\n{chain}\n"
        f"MOMENTUM: {state.get('momentum')}\n"
        f"Last message: {last_user}"
    )

    response_b = call_model(client, [
        {"role": "system", "content": "You are continuing a transferred reasoning thread."},
        {"role": "user",   "content": recon},
    ], label="Qwen (Session B)")

    return response_b, last_user


def phase4_cold_start(client, last_user):
    """Cold start — zero context, same last message."""
    print(f"\n{BOLD}Phase 4 — Cold Start (no context){RESET}\n")

    response_cold = call_model(client, [
        {"role": "system", "content": "You are a thoughtful assistant."},
        {"role": "user",   "content": last_user},
    ], label="Qwen (Cold Start)")

    return response_cold


def phase5_score(client, state, response_b, response_cold):
    """Score Semantic Continuity Score (SCS) 0–1 using { scanning."""
    print(f"\n{BOLD}Phase 5 — Semantic Continuity Score{RESET}")
    print(f"{PURPLE}[SCS Scorer]{RESET} Evaluating continuity...", end="", flush=True)

    prompt = SCS_PROMPT.format(
        intent=state.get("intent", ""),
        momentum=state.get("momentum", ""),
        response_b=response_b[:1200],
        response_cold=response_cold[:1200],
    )

    raw = call_model(client, [{"role": "user", "content": prompt}], stream=False)

    fallback_scores = {
        "session_b_scs": 0.0,
        "cold_start_scs": 0.0,
        "explanation": "scoring failed",
    }
    scores = parse_json(raw, fallback_scores)

    if scores is fallback_scores:
        print(f" {AMBER}parse error — using fallback{RESET}")
    else:
        print(f" {GREEN}done{RESET}")

    # Clamp scores to [0.0, 1.0]
    for key in ("session_b_scs", "cold_start_scs"):
        try:
            scores[key] = max(0.0, min(1.0, float(scores.get(key, 0.0))))
        except (TypeError, ValueError):
            scores[key] = 0.0

    return scores


# ── Main ──────────────────────────────────────────────────────────────────────

def run_csp():
    print(f"\n{PURPLE}{'='*62}{RESET}")
    print(f"  {BOLD}Cognitive State Protocol v0.2{RESET}")
    print(f"  Model : {MODEL}")
    print(f"  Log   : {LOG_FILE}")
    print(f"{PURPLE}{'='*62}{RESET}")

    client = Groq(api_key=get_api_key())

    conversation               = phase1_conversation(client)
    packet, state, ratio       = phase2_extract(client, conversation)
    response_b, last_user      = phase3_send(client, state, conversation)
    response_cold              = phase4_cold_start(client, last_user)
    scores                     = phase5_score(client, state, response_b, response_cold)

    b    = scores.get("session_b_scs", 0.0)
    cold = scores.get("cold_start_scs", 0.0)
    gain = b / max(cold, 0.01)

    print(f"\n  {TEAL}Session B SCS:{RESET}   {BOLD}{b:.3f}{RESET}")
    print(f"  {DIM}Cold start:{RESET}      {cold:.3f}")
    print(f"  {GREEN}Gain:{RESET}            {gain:.2f}x")
    print(f"  {GREEN}Compression:{RESET}     {ratio:.1f}x")
    print(f"  {DIM}Verdict:{RESET}         {scores.get('explanation', '')}")

    if b >= 0.85:
        print(f"\n  {GREEN}TARGET MET: SCS {b*100:.0f}% >= 85%{RESET}\n")
    else:
        print(f"\n  {AMBER}SCS {b*100:.0f}% — {85 - b*100:.0f}% below target{RESET}\n")

    log_entry = {
        "timestamp":   datetime.datetime.now().isoformat(),
        "packet_id":   packet["packet_id"],
        "compression": round(ratio, 2),
        "scs_b":       b,
        "scs_cold":    cold,
        "gain":        round(gain, 3),
        "intent":      state.get("intent", ""),
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"  {DIM}Logged to {LOG_FILE}{RESET}\n")


if __name__ == "__main__":
    run_csp()
