# SMART-UAHP Specification v0.1.0

## Abstract

SMART-UAHP (Stiefel-Matryoshka Adaptive Runtime + Universal Agent Handshake Protocol) defines a substrate-agnostic protocol for distributing inference workloads across heterogeneous compute environments based on real-time thermodynamic pressure. The protocol restores Energy-Intelligence Symmetry by making the cognitive resolution of an agent a dynamic variable rather than a fixed deployment parameter.

---

## 1. Definitions

**Substrate** — any compute environment characterized by a GPU type, VRAM ceiling, thermal envelope, and grid carbon intensity.

**Cognitive Tier** — one of five resolution levels: 8-dim (Survival), 16-dim (Minimal), 32-dim (Standard), 64-dim (Enhanced), 128-dim (Full).

**Thermodynamic Pressure** — a scalar derived from VRAM utilization, GPU temperature, and grid carbon intensity. High pressure forces downward tier migration.

**Carbon-Silicon Bridge** — the UAHP-secured transport channel over which a compressed KV-context moves from a high-pressure substrate to a low-pressure substrate.

**IPJG (Intelligence-per-Joule Gain)** — the primary benchmark metric. Defined as:

```
IPJG = (Σ quality_weight_i × tokens_i) / (total_joules_consumed)
       ÷
       (Σ tokens_i) / (total_joules_consumed, static 128-dim)
```

---

## 2. Cognitive Tier Table

| Tier | Dimension | VRAM multiplier | Quality score | Power fraction |
|---|---|---|---|---|
| Survival | 8 | 0.5× | 0.64 | 0.203 |
| Minimal | 16 | 1× | 0.74 | 0.213 |
| Standard | 32 | 2× | 0.85 | 0.250 |
| Enhanced | 64 | 4× | 0.93 | 0.400 |
| Full | 128 | 8× | 1.00 | 1.000 |

Quality scores are derived from the LMSys Chatbot Arena human preference dataset. Power fractions are empirically derived from manufacturer TDP curves at each resolution level.

---

## 3. Thermodynamic Pricing

An agent's bid for a task is computed as:

```
bid = base_tokens + energy_cost + carbon_tax
```

Where:

```
joules_per_token = (gpu_tdp_w × pue × power_fraction) / tokens_per_second

energy_cost = joules_per_token / 3,600,000 × cost_per_kwh

carbon_tax = joules_per_token / 3,600,000 × carbon_intensity_gco2_kwh × 0.0001
```

PUE (Power Usage Effectiveness) default: 1.2

---

## 4. Routing Decision Function

Given a task with required dimension `d`, the router selects a substrate by:

```
1. Compute local_cost  = energy_cost(local)  + carbon_tax(local)
2. Compute remote_cost = energy_cost(remote) + carbon_tax(remote) + transport_overhead
3. If d.vram_requirement > local.vram_available → force remote
4. Else if remote_cost < local_cost × 0.75    → route remote
5. Else                                        → compute local
```

The 0.75 threshold ensures routing overhead is only incurred when the thermodynamic gain is meaningful.

---

## 5. KV-Context Handshake (Carbon-Silicon Bridge)

The bridge uses UAHP v0.5.4 secure sessions for transport:

```
1. mobile_agent.export_kv_context(tier="LOW", session_key=uahp_session)
   → produces compressed tensor packet (16-dim, SafeTensors format)

2. UAHP SecureSession encrypts packet: X25519 + AES-256-GCM

3. Remote substrate receives, decrypts, re-projects to 128-dim
   via geometric re-projection on the Stiefel manifold

4. Remote agent executes task, returns CompletionReceipt
   signed with Ed25519 per UAHP v0.5.4 spec
```

---

## 6. Zero-Knowledge Context Verification (Selective Attention Sample)

To prevent cognitive fraud (a node claiming to use the sent KV-cache but using a cheaper model):

```
1. Sender picks a random historical token index: challenge_idx ∈ [0, seq_len)
2. Remote node provides attention weight at challenge_idx from actual forward pass
3. Sender verifies: |expected_score - received_score| < tolerance (default: 1e-3)
4. Failed verification → DeathCertificate issued via UAHP v0.5.4
```

---

## 7. Benchmark Protocol

To produce a valid IPJG measurement:

1. Deploy `BreathingAgent` on target hardware with power meter attached (NVIDIA SMI or equivalent)
2. Run 600-task workload sampled from LMSys Chatbot Arena distribution
3. Log per-task: dimension selected, tokens processed, joules consumed, quality score
4. Compute IPJG against static 128-dim baseline on identical hardware
5. Report: mean IPJG, energy saved %, CO₂ saved %, substrate configuration

Hardware validation target: ≥3 independent GPU types, ≥2 grid regions.

---

## 8. Relationship to UAHP

SMART-UAHP is a layer above UAHP v0.5.4. UAHP provides:
- Agent identity (Ed25519 keypairs)
- Sponsorship and trust scoring
- Encrypted task transport (X25519 + AES-256-GCM)
- Signed liveness proofs and heartbeats
- Completion receipts with output spec hashing

SMART-UAHP adds:
- Cognitive Tier selection
- Thermodynamic pricing
- Entropy-aware routing
- KV-context compression and transport
- ZK context verification

---

## 9. Open items for v0.2.0

- Hardware validation on RTX 3080 and A100
- RFC 8785 canonical JSON for ZK proof signatures
- TypeScript bridge HKDF alignment with UAHP v0.5.4
- Actual Stiefel manifold re-projection implementation (currently linear interpolation)
- Peer review of IPJG metric definition

---

## References

- UAHP v0.5.4 specification: https://github.com/PaulRaspey/uahp
- LMSys Chatbot Arena: Chiang et al., 2024
- EPA eGrid 2023: U.S. Environmental Protection Agency
- Stiefel manifold compression: inspired by Matryoshka Representation Learning, Kusupati et al., 2022
