"""
examples/getting_started.py

Run this to see SMART-UAHP working end to end.
No GPU required — uses mock hardware state.

Usage:
    python examples/getting_started.py
"""

from smart_uahp import (
    EnergyProfile,
    ThermodynamicNegotiator,
    GPUMonitor,
    GPUState,
    BreathingAgent,
    CognitiveTier,
    TaskComplexity,
    EntropyAwareRouter,
)


def demo_thermodynamics():
    print("=" * 55)
    print("1. THERMODYNAMIC PRICING")
    print("=" * 55)
    print("Comparing the true cost of the same task across")
    print("all five cognitive tiers on a Texas RTX 4090.\n")

    profile    = EnergyProfile(grid_region="ERCOT", gpu_model="RTX_4090")
    negotiator = ThermodynamicNegotiator(profile)
    tiers      = negotiator.compare_tiers("demo_task", token_count=500)

    print(f"  {'Tier':<12} {'Dim':<6} {'$/token':<14} {'Joules':<12} {'gCO2'}")
    print("  " + "-" * 55)
    for t in tiers:
        print(
            f"  {'':<12} {t['rank']:<6} "
            f"{t['cost_per_token']:<14.8f} "
            f"{t['energy_joules']:<12.6f} "
            f"{t['carbon_grams']:.6f}"
        )
    print()


def demo_breathing():
    print("=" * 55)
    print("2. BREATHING AGENT — COGNITIVE ELASTICITY")
    print("=" * 55)
    print("Watch the agent scale its resolution as GPU")
    print("pressure increases.\n")

    monitor = GPUMonitor(vram_total_gb=24.0, tdp_w=450.0)
    agent   = BreathingAgent(monitor=monitor)

    scenarios = [
        ("low_pressure",    50,   CognitiveTier.FULL,     GPUState.mock(0.25, 52.0)),
        ("normal",         450,   CognitiveTier.STANDARD, GPUState.mock(0.55, 65.0)),
        ("high_pressure",  900,   CognitiveTier.ENHANCED, GPUState.mock(0.82, 76.0)),
        ("thermal_limit", 2200,   CognitiveTier.FULL,     GPUState.mock(0.91, 88.0)),
    ]

    for task_id, tokens, req_tier, state in scenarios:
        monitor.read_state = lambda s=state: s
        task = TaskComplexity(task_id, token_estimate=tokens, required_tier=req_tier)
        tier, quality, reason = agent.select_tier(task)
        savings = agent.vram_savings_vs_full()
        print(f"  [{task_id}]")
        print(f"  Required: {req_tier.name:<10} Selected: {tier.name} ({tier.value}-dim)")
        print(f"  Quality:  {quality:.0%}            VRAM saved: {savings:.0f}%")
        print(f"  Reason:   {reason}\n")


def demo_routing():
    print("=" * 55)
    print("3. ENTROPY-AWARE ROUTING")
    print("=" * 55)
    print("Routing between Texas (coal) and Pacific NW (hydro).")
    print("Watch tasks migrate to the cleaner substrate.\n")

    local_profile  = EnergyProfile(grid_region="ERCOT", gpu_model="RTX_4090")
    remote_profile = EnergyProfile(grid_region="NWPP",  gpu_model="A100_80GB")
    router         = EntropyAwareRouter(local_profile, remote_profile)

    tasks = [
        TaskComplexity("hello",         50,   CognitiveTier.SURVIVAL),
        TaskComplexity("summarize_doc", 450,  CognitiveTier.STANDARD),
        TaskComplexity("write_paper",  2200,  CognitiveTier.FULL),
    ]

    for task in tasks:
        result = router.route(task)
        s = result.summary()
        arrow = "→ LOCAL " if s["decision"] == "LOCAL" else "→ REMOTE"
        print(f"  {task.task_id:<20} {arrow}  savings: {s['savings_pct']:.0f}%")
        print(f"  {s['reason']}\n")

    stats = router.aggregate_stats()
    print(f"  Summary: {stats['remote_pct']}% tasks routed remote")
    print(f"  Mean energy savings: {stats['mean_savings_pct']}%\n")


if __name__ == "__main__":
    print("\nSMART-UAHP v0.1.0 — Getting Started Demo\n")
    demo_thermodynamics()
    demo_breathing()
    demo_routing()
    print("=" * 55)
    print("Done. See smart_uahp/ for full module source.")
    print("=" * 55)
