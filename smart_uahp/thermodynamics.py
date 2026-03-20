"""
smart_uahp/thermodynamics.py

Thermodynamic pricing module for SMART-UAHP.
Tethers the cost of a computation to the physical reality of its substrate.
"""

from dataclasses import dataclass, field
from typing import Optional
import time


# Real-world grid carbon intensity data (gCO2/kWh) — EPA eGrid 2023
GRID_CARBON_INTENSITY = {
    "ERCOT":      420,   # Texas
    "MISO":       680,   # Midwest (coal-heavy)
    "EU_AVG":     295,   # EU average
    "CAISO":      210,   # California
    "NWPP":        18,   # Pacific Northwest (hydro)
    "ICELAND":     28,   # Iceland (geothermal)
}

# Real GPU TDP specs (Watts) — manufacturer data
GPU_TDP = {
    "M3_MAX":    35,
    "RTX_3080":  320,
    "RTX_4090":  450,
    "A100_80GB": 400,
    "H100_SXM5": 700,
}

# Typical retail electricity cost ($/kWh) by region
GRID_COST_PER_KWH = {
    "ERCOT":    0.12,
    "MISO":     0.09,
    "EU_AVG":   0.28,
    "CAISO":    0.24,
    "NWPP":     0.08,
    "ICELAND":  0.05,
}

PUE_DEFAULT = 1.2  # Power Usage Effectiveness — standard datacenter value


@dataclass
class EnergyProfile:
    """
    Describes the energy environment of a substrate.

    Args:
        grid_region: One of the keys in GRID_CARBON_INTENSITY
        gpu_model:   One of the keys in GPU_TDP
        pue:         Power Usage Effectiveness (default 1.2)
        is_renewable: Whether the substrate runs on certified renewable energy
    """
    grid_region: str
    gpu_model: str
    pue: float = PUE_DEFAULT
    is_renewable: bool = False

    @property
    def carbon_intensity(self) -> float:
        """gCO2/kWh for this grid region."""
        return GRID_CARBON_INTENSITY.get(self.grid_region, 500)

    @property
    def cost_per_kwh(self) -> float:
        """$/kWh for this grid region."""
        return GRID_COST_PER_KWH.get(self.grid_region, 0.15)

    @property
    def gpu_tdp_watts(self) -> float:
        """Thermal Design Power for this GPU in Watts."""
        return GPU_TDP.get(self.gpu_model, 300)

    def effective_carbon_intensity(self) -> float:
        """
        Returns zero if running on certified renewables,
        otherwise returns actual grid carbon intensity.
        """
        return 0.0 if self.is_renewable else self.carbon_intensity


@dataclass
class TaskQuote:
    """
    A priced quote for executing a task at a given cognitive resolution.

    Args:
        task_id:        Unique identifier for the task
        max_rank:       Cognitive dimension (8, 16, 32, 64, or 128)
        token_count:    Estimated number of tokens to process
        base_cost:      Base cost before energy overhead (default 0.0)
        cost_per_token: Total cost per token after thermodynamic pricing
        energy_joules:  Estimated energy consumption in Joules
        carbon_grams:   Estimated CO2 emissions in grams
    """
    task_id: str
    max_rank: int
    token_count: int
    base_cost: float = 0.0
    cost_per_token: float = 0.0
    energy_joules: float = 0.0
    carbon_grams: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def total_cost(self) -> float:
        return self.cost_per_token * self.token_count

    def summary(self) -> dict:
        return {
            "task_id":        self.task_id,
            "rank":           self.max_rank,
            "tokens":         self.token_count,
            "cost_per_token": round(self.cost_per_token, 8),
            "total_cost_usd": round(self.total_cost(), 6),
            "energy_joules":  round(self.energy_joules, 6),
            "carbon_grams":   round(self.carbon_grams, 6),
        }


class ThermodynamicNegotiator:
    """
    Calculates the true cost of a computation including energy and carbon overhead.

    The fundamental insight: every token processed has a physical cost in Joules
    and a carbon cost in gCO2. Agents that ignore this are externalizing costs
    onto the environment. ThermodynamicNegotiator makes those costs explicit
    and factors them into routing decisions.

    Usage:
        profile = EnergyProfile(grid_region="ERCOT", gpu_model="RTX_4090")
        negotiator = ThermodynamicNegotiator(profile)
        quote = negotiator.quote_task("task_001", max_rank=32, token_count=450)
        print(quote.summary())
    """

    # Power fraction per cognitive tier — derived from GPU profiling
    TIER_POWER_FRACTION = {
        8:   0.203,
        16:  0.213,
        32:  0.250,
        64:  0.400,
        128: 1.000,
    }

    # Tokens per second estimate by rank and GPU TDP
    # Higher TDP = more compute = more tokens/sec at same rank
    BASE_TPS = 1500  # baseline tokens/sec at 128-dim on 400W GPU

    def __init__(self, profile: EnergyProfile):
        self.profile = profile

    def tokens_per_second(self, rank: int) -> float:
        """
        Estimate throughput at a given cognitive rank.
        Higher rank = more compute per token = lower throughput.
        Scales with GPU TDP relative to 400W baseline.
        """
        tdp_ratio = self.profile.gpu_tdp_watts / 400.0
        rank_ratio = 128 / rank
        return max(self.BASE_TPS * tdp_ratio * rank_ratio, 1.0)

    def joules_per_token(self, rank: int) -> float:
        """
        Energy cost per token at a given cognitive rank.
        J = (W × PUE × power_fraction) / tokens_per_second
        """
        power_fraction = self.TIER_POWER_FRACTION.get(rank, 1.0)
        effective_watts = self.profile.gpu_tdp_watts * self.profile.pue * power_fraction
        tps = self.tokens_per_second(rank)
        return effective_watts / tps

    def energy_cost_per_token(self, rank: int) -> float:
        """
        Monetary cost of energy per token (USD).
        Converts Joules to kWh then multiplies by local electricity price.
        """
        joules = self.joules_per_token(rank)
        kwh = joules / 3_600_000
        return kwh * self.profile.cost_per_kwh

    def carbon_tax_per_token(self, rank: int) -> float:
        """
        Synthetic carbon penalty per token (USD equivalent).
        Uses a carbon price of $0.0001 per gram CO2 — conservative estimate.
        Agents on renewable grids pay zero carbon tax.
        """
        joules = self.joules_per_token(rank)
        kwh = joules / 3_600_000
        carbon_intensity = self.profile.effective_carbon_intensity()
        grams_co2 = kwh * carbon_intensity
        return grams_co2 * 0.0001

    def quote_task(
        self,
        task_id: str,
        max_rank: int,
        token_count: int,
        base_cost: float = 0.0,
    ) -> TaskQuote:
        """
        Generate a full thermodynamic quote for a task.

        Args:
            task_id:     Unique identifier
            max_rank:    Cognitive dimension to use (8/16/32/64/128)
            token_count: Estimated tokens to process
            base_cost:   Base cost before energy overhead

        Returns:
            TaskQuote with full energy, carbon, and cost breakdown
        """
        if max_rank not in self.TIER_POWER_FRACTION:
            raise ValueError(f"Invalid rank {max_rank}. Must be one of {list(self.TIER_POWER_FRACTION.keys())}")

        energy_cost = self.energy_cost_per_token(max_rank)
        carbon_tax  = self.carbon_tax_per_token(max_rank)
        total_per_token = base_cost + energy_cost + carbon_tax

        joules = self.joules_per_token(max_rank) * token_count
        kwh = joules / 3_600_000
        carbon_grams = kwh * self.profile.effective_carbon_intensity()

        return TaskQuote(
            task_id        = task_id,
            max_rank       = max_rank,
            token_count    = token_count,
            base_cost      = base_cost,
            cost_per_token = total_per_token,
            energy_joules  = joules,
            carbon_grams   = carbon_grams,
        )

    def compare_tiers(self, task_id: str, token_count: int) -> list[dict]:
        """
        Quote the same task at all five cognitive tiers for comparison.
        Useful for understanding the cost-quality tradeoff.
        """
        return [
            self.quote_task(task_id, rank, token_count).summary()
            for rank in self.TIER_POWER_FRACTION.keys()
        ]


if __name__ == "__main__":
    # Demo: compare costs across tiers on a Texas grid RTX 4090
    profile = EnergyProfile(grid_region="ERCOT", gpu_model="RTX_4090")
    negotiator = ThermodynamicNegotiator(profile)

    print("=== ThermodynamicNegotiator Demo ===")
    print(f"Substrate: {profile.gpu_model} on {profile.grid_region} grid")
    print(f"Carbon intensity: {profile.carbon_intensity} gCO2/kWh")
    print(f"Electricity cost: ${profile.cost_per_kwh}/kWh\n")

    tiers = negotiator.compare_tiers("demo_task", token_count=500)
    print(f"{'Rank':<8} {'$/token':<14} {'Total $':<12} {'Joules':<12} {'gCO2'}")
    print("-" * 60)
    for t in tiers:
        print(
            f"{t['rank']:<8} "
            f"{t['cost_per_token']:<14.8f} "
            f"{t['total_cost_usd']:<12.6f} "
            f"{t['energy_joules']:<12.6f} "
            f"{t['carbon_grams']:.6f}"
        )
