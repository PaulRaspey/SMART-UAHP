"""
smart_uahp/router.py

Entropy-Aware Router — decides whether to compute locally or migrate
a task to a remote substrate via the Carbon-Silicon Bridge.

The routing decision is thermodynamically rational:
migrate only when the energy cost of migration is less than
the energy saved by computing on the more efficient remote substrate.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
import logging

from .thermodynamics import ThermodynamicNegotiator, EnergyProfile, TaskQuote
from .breathing import BreathingAgent, CognitiveTier, TaskComplexity, GPUMonitor

logger = logging.getLogger(__name__)


class RoutingDecision(Enum):
    LOCAL   = "LOCAL"
    REMOTE  = "REMOTE"
    FORCED_REMOTE = "FORCED_REMOTE"  # No local VRAM available


# VRAM required per cognitive tier (GB) — based on Llama 3 8B profile
TIER_VRAM_REQUIRED_GB = {
    CognitiveTier.SURVIVAL:  0.5,
    CognitiveTier.MINIMAL:   1.0,
    CognitiveTier.STANDARD:  2.0,
    CognitiveTier.ENHANCED:  4.0,
    CognitiveTier.FULL:      8.0,
}

# Transport overhead — energy cost of sending a compressed KV packet (Joules)
# Based on typical WiFi/LAN power draw for a ~50KB compressed tensor packet
TRANSPORT_OVERHEAD_JOULES = 0.003


@dataclass
class RoutingResult:
    """
    The output of a routing decision.

    Attributes:
        decision:       LOCAL, REMOTE, or FORCED_REMOTE
        local_quote:    Cost estimate for local execution
        remote_quote:   Cost estimate for remote execution
        selected_quote: The quote for the chosen substrate
        reason:         Human-readable explanation
        savings_pct:    Energy savings percentage vs the alternative
    """
    decision:       RoutingDecision
    local_quote:    TaskQuote
    remote_quote:   TaskQuote
    selected_quote: TaskQuote
    reason:         str
    savings_pct:    float

    def summary(self) -> dict:
        return {
            "decision":        self.decision.value,
            "selected_rank":   self.selected_quote.max_rank,
            "local_joules":    round(self.local_quote.energy_joules, 6),
            "remote_joules":   round(self.remote_quote.energy_joules + TRANSPORT_OVERHEAD_JOULES, 6),
            "local_carbon_g":  round(self.local_quote.carbon_grams, 6),
            "remote_carbon_g": round(self.remote_quote.carbon_grams, 6),
            "savings_pct":     round(self.savings_pct, 1),
            "reason":          self.reason,
        }


class EntropyAwareRouter:
    """
    Routes tasks between local and remote substrates based on
    thermodynamic cost comparison.

    Routing logic:
    1. If local VRAM is insufficient → FORCED_REMOTE
    2. If remote total cost < local total cost × threshold → REMOTE
    3. Otherwise → LOCAL

    The "total cost" includes both energy cost ($/token) and a carbon
    tax term, making the router inherently carbon-aware.

    Usage:
        local_profile  = EnergyProfile("ERCOT",    "RTX_4090")
        remote_profile = EnergyProfile("NWPP",     "A100_80GB")
        monitor        = GPUMonitor(vram_total_gb=24.0, tdp_w=450.0)

        router = EntropyAwareRouter(
            local_profile  = local_profile,
            remote_profile = remote_profile,
            monitor        = monitor,
        )

        task   = TaskComplexity("task_001", token_estimate=450, required_tier=CognitiveTier.STANDARD)
        result = router.route(task)
        print(result.summary())
    """

    # Route remote only when it's at least this much cheaper
    MIGRATION_THRESHOLD = 0.75  # remote must cost < 75% of local

    def __init__(
        self,
        local_profile:   EnergyProfile,
        remote_profile:  EnergyProfile,
        monitor:         Optional[GPUMonitor] = None,
        vram_available_gb: float = 24.0,
    ):
        self.local_negotiator  = ThermodynamicNegotiator(local_profile)
        self.remote_negotiator = ThermodynamicNegotiator(remote_profile)
        self.monitor           = monitor or GPUMonitor(
            vram_total_gb=vram_available_gb,
            tdp_w=local_profile.gpu_tdp_watts,
        )
        self.vram_available_gb = vram_available_gb
        self._routing_log: list[dict] = []

    def _vram_sufficient(self, tier: CognitiveTier) -> bool:
        required = TIER_VRAM_REQUIRED_GB.get(tier, 8.0)
        state    = self.monitor.read_state()
        available = state.vram_total_gb - state.vram_used_gb
        return available >= required

    def route(self, task: TaskComplexity) -> RoutingResult:
        """
        Make a thermodynamically-rational routing decision for a task.

        Args:
            task: TaskComplexity describing the work to be done

        Returns:
            RoutingResult with full cost comparison and decision rationale
        """
        tier = task.required_tier

        local_quote  = self.local_negotiator.quote_task(
            task.task_id, tier.value, task.token_estimate
        )
        remote_quote = self.remote_negotiator.quote_task(
            task.task_id, tier.value, task.token_estimate
        )

        # Add transport overhead to remote cost
        remote_total_joules = remote_quote.energy_joules + TRANSPORT_OVERHEAD_JOULES

        # Check VRAM availability
        if not self._vram_sufficient(tier):
            result = RoutingResult(
                decision       = RoutingDecision.FORCED_REMOTE,
                local_quote    = local_quote,
                remote_quote   = remote_quote,
                selected_quote = remote_quote,
                reason         = f"insufficient local VRAM for {tier.name} tier",
                savings_pct    = (1.0 - remote_total_joules / max(local_quote.energy_joules, 1e-12)) * 100,
            )
            self._log(result, task)
            return result

        # Thermodynamic comparison
        local_cost  = local_quote.cost_per_token
        remote_cost = remote_quote.cost_per_token + (TRANSPORT_OVERHEAD_JOULES / max(task.token_estimate, 1)) * 0.001

        if remote_cost < local_cost * self.MIGRATION_THRESHOLD:
            savings = (1.0 - remote_total_joules / max(local_quote.energy_joules, 1e-12)) * 100
            result = RoutingResult(
                decision       = RoutingDecision.REMOTE,
                local_quote    = local_quote,
                remote_quote   = remote_quote,
                selected_quote = remote_quote,
                reason         = (
                    f"remote cost ({remote_cost:.2e} $/token) < "
                    f"{int(self.MIGRATION_THRESHOLD*100)}% of local ({local_cost:.2e} $/token)"
                ),
                savings_pct    = savings,
            )
        else:
            savings = (1.0 - local_quote.energy_joules / max(remote_total_joules, 1e-12)) * 100
            result = RoutingResult(
                decision       = RoutingDecision.LOCAL,
                local_quote    = local_quote,
                remote_quote   = remote_quote,
                selected_quote = local_quote,
                reason         = (
                    f"local cost ({local_cost:.2e} $/token) within threshold of "
                    f"remote ({remote_cost:.2e} $/token)"
                ),
                savings_pct    = max(0.0, savings),
            )

        self._log(result, task)
        return result

    def _log(self, result: RoutingResult, task: TaskComplexity):
        entry = {"task_id": task.task_id, **result.summary()}
        self._routing_log.append(entry)
        logger.info(
            f"[Router] task={task.task_id} decision={result.decision.value} "
            f"savings={result.savings_pct:.1f}% reason={result.reason}"
        )

    def routing_log(self) -> list[dict]:
        return list(self._routing_log)

    def aggregate_stats(self) -> dict:
        """Summarize routing decisions across all tasks."""
        if not self._routing_log:
            return {}
        total   = len(self._routing_log)
        remote  = sum(1 for r in self._routing_log if r["decision"] != "LOCAL")
        savings = [r["savings_pct"] for r in self._routing_log]
        return {
            "total_tasks":     total,
            "remote_routed":   remote,
            "local_routed":    total - remote,
            "remote_pct":      round(remote / total * 100, 1),
            "mean_savings_pct": round(sum(savings) / len(savings), 1),
            "max_savings_pct": round(max(savings), 1),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== EntropyAwareRouter Demo ===\n")

    local_profile  = EnergyProfile(grid_region="ERCOT",  gpu_model="RTX_4090")
    remote_profile = EnergyProfile(grid_region="NWPP",   gpu_model="A100_80GB")

    router = EntropyAwareRouter(
        local_profile    = local_profile,
        remote_profile   = remote_profile,
        vram_available_gb = 24.0,
    )

    tasks = [
        TaskComplexity("simple_greeting",   50,   CognitiveTier.SURVIVAL),
        TaskComplexity("code_completion",   450,  CognitiveTier.STANDARD),
        TaskComplexity("deep_research",    2200,  CognitiveTier.FULL),
        TaskComplexity("complex_analysis",  900,  CognitiveTier.ENHANCED),
    ]

    for task in tasks:
        result = router.route(task)
        s = result.summary()
        print(f"Task:     {task.task_id}")
        print(f"Decision: {s['decision']} | Savings: {s['savings_pct']}%")
        print(f"Local:    {s['local_joules']:.4f}J  {s['local_carbon_g']:.4f}gCO2")
        print(f"Remote:   {s['remote_joules']:.4f}J  {s['remote_carbon_g']:.4f}gCO2")
        print(f"Reason:   {s['reason']}\n")

    print("=== Aggregate Stats ===")
    stats = router.aggregate_stats()
    for k, v in stats.items():
        print(f"{k}: {v}")
