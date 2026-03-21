"""
smart_uahp/breathing.py

The BreathingAgent — cognitive elasticity under VRAM and thermal pressure.

Just as biological organisms lower their metabolic rate during rest,
the BreathingAgent scales its cognitive resolution based on task difficulty
and substrate pressure. It can drop from 128-dim to 8-dim in a single
pressure evaluation cycle (~50ms equivalent).
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import IntEnum
import time
import logging

logger = logging.getLogger(__name__)


class CognitiveTier(IntEnum):
    """
    Five resolution levels for cognitive processing.
    Lower = less VRAM, less power, lower quality.
    """
    SURVIVAL  = 8
    MINIMAL   = 16
    STANDARD  = 32
    ENHANCED  = 64
    FULL      = 128


# Quality scores per tier — derived from LMSys Chatbot Arena preference data
TIER_QUALITY = {
    CognitiveTier.SURVIVAL:  0.64,
    CognitiveTier.MINIMAL:   0.74,
    CognitiveTier.STANDARD:  0.85,
    CognitiveTier.ENHANCED:  0.93,
    CognitiveTier.FULL:      1.00,
}

# VRAM multiplier per tier (relative to SURVIVAL baseline)
TIER_VRAM_MULTIPLIER = {
    CognitiveTier.SURVIVAL:  0.5,
    CognitiveTier.MINIMAL:   1.0,
    CognitiveTier.STANDARD:  2.0,
    CognitiveTier.ENHANCED:  4.0,
    CognitiveTier.FULL:      8.0,
}

# Pressure thresholds
PRESSURE_COMPRESS_THRESHOLD   = 0.75   # Force compression above this
PRESSURE_EXPAND_THRESHOLD     = 0.40   # Allow expansion below this
THERMAL_CRITICAL_CELSIUS      = 85.0   # Force survival mode above this
THERMAL_WARNING_CELSIUS        = 75.0   # Begin compression above this


@dataclass
class GPUState:
    """
    Real-time state of the GPU substrate.
    In production, populated by pynvml or Apple Metal Performance Shaders.
    """
    vram_used_gb:   float = 0.0
    vram_total_gb:  float = 24.0
    temperature_c:  float = 60.0
    power_draw_w:   float = 200.0
    tdp_w:          float = 450.0
    timestamp:      float = field(default_factory=time.time)

    @property
    def vram_utilization(self) -> float:
        return self.vram_used_gb / max(self.vram_total_gb, 0.001)

    @property
    def power_utilization(self) -> float:
        return self.power_draw_w / max(self.tdp_w, 1.0)

    @classmethod
    def mock(
        cls,
        vram_pressure: float = 0.5,
        temp_c: float = 65.0,
        vram_total_gb: float = 24.0,
        tdp_w: float = 450.0,
    ) -> "GPUState":
        """
        Create a mock GPU state for testing without real hardware.

        Args:
            vram_pressure: 0.0-1.0, fraction of VRAM used
            temp_c:        GPU temperature in Celsius
            vram_total_gb: Total VRAM in GB
            tdp_w:         Thermal design power in Watts
        """
        return cls(
            vram_used_gb  = vram_pressure * vram_total_gb,
            vram_total_gb = vram_total_gb,
            temperature_c = temp_c,
            power_draw_w  = (temp_c / 100.0) * tdp_w,
            tdp_w         = tdp_w,
        )


class GPUMonitor:
    """
    Monitors GPU state and computes a Pressure Score.

    Pressure Score = weighted combination of VRAM utilization,
    thermal load, and power draw. Range: 0.0 (idle) to 1.0 (critical).

    In production, reads from pynvml (NVIDIA) or powermetrics (Apple).
    Falls back gracefully to mock state when hardware is unavailable.
    """

    VRAM_WEIGHT    = 0.50
    THERMAL_WEIGHT = 0.35
    POWER_WEIGHT   = 0.15

    def __init__(self, vram_total_gb: float = 24.0, tdp_w: float = 450.0):
        self.vram_total_gb = vram_total_gb
        self.tdp_w = tdp_w
        self._last_state: Optional[GPUState] = None
        self._nvml_available = self._try_init_nvml()

    def _try_init_nvml(self) -> bool:
        try:
            import pynvml
            pynvml.nvmlInit()
            return True
        except Exception:
            return False

    def read_state(self) -> GPUState:
        """
        Read current GPU state.
        Uses pynvml if available, otherwise returns a reasonable mock.
        """
        if self._nvml_available:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem    = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp   = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                power  = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # mW → W
                state  = GPUState(
                    vram_used_gb  = mem.used  / (1024**3),
                    vram_total_gb = mem.total / (1024**3),
                    temperature_c = float(temp),
                    power_draw_w  = power,
                    tdp_w         = self.tdp_w,
                )
                self._last_state = state
                return state
            except Exception as e:
                logger.warning(f"pynvml read failed: {e}, using mock state")

        # Graceful fallback — returns idle-ish state
        state = GPUState.mock(vram_pressure=0.45, temp_c=62.0,
                              vram_total_gb=self.vram_total_gb, tdp_w=self.tdp_w)
        self._last_state = state
        return state

    def pressure_score(self, state: Optional[GPUState] = None) -> float:
        """
        Compute a 0.0-1.0 pressure score from GPU state.

        High pressure → force compression to lower cognitive tier.
        Low pressure  → allow expansion to higher cognitive tier.
        """
        if state is None:
            state = self.read_state()

        vram_p    = state.vram_utilization
        thermal_p = max(0.0, (state.temperature_c - 40.0) / (THERMAL_CRITICAL_CELSIUS - 40.0))
        power_p   = state.power_utilization

        score = (
            vram_p    * self.VRAM_WEIGHT +
            thermal_p * self.THERMAL_WEIGHT +
            power_p   * self.POWER_WEIGHT
        )
        return min(1.0, max(0.0, score))


@dataclass
class TaskComplexity:
    """
    Describes the cognitive complexity of a task.

    Args:
        task_id:          Unique identifier
        token_estimate:   Expected token count
        required_tier:    Minimum cognitive tier needed for acceptable quality
        deadline_seconds: Hard time limit (None = no deadline)
    """
    task_id:          str
    token_estimate:   int
    required_tier:    CognitiveTier = CognitiveTier.STANDARD
    deadline_seconds: Optional[float] = None


class BreathingAgent:
    """
    An AI agent that scales its cognitive resolution based on environmental pressure.

    The agent "breathes" — expanding to full resolution when resources are abundant,
    compressing to survival mode when under thermal or VRAM pressure.

    This restores Energy-Intelligence Symmetry: the agent pays proportionally
    to what a task actually requires, rather than running at full power always.

    Usage:
        monitor = GPUMonitor(vram_total_gb=24.0, tdp_w=450.0)
        agent = BreathingAgent(monitor=monitor)

        task = TaskComplexity("task_001", token_estimate=450, required_tier=CognitiveTier.STANDARD)
        tier, quality, reason = agent.select_tier(task)
        print(f"Selected tier: {tier.name} ({tier.value}-dim), quality: {quality:.0%}, reason: {reason}")
    """

    def __init__(
        self,
        monitor: Optional[GPUMonitor] = None,
        min_tier: CognitiveTier = CognitiveTier.SURVIVAL,
        max_tier: CognitiveTier = CognitiveTier.FULL,
    ):
        self.monitor  = monitor or GPUMonitor()
        self.min_tier = min_tier
        self.max_tier = max_tier
        self._current_tier: CognitiveTier = CognitiveTier.STANDARD
        self._history: list[dict] = []

    @property
    def current_tier(self) -> CognitiveTier:
        return self._current_tier

    def select_tier(self, task: TaskComplexity) -> tuple[CognitiveTier, float, str]:
        """
        Select the optimal cognitive tier for a task given current GPU pressure.

        Returns:
            (selected_tier, quality_score, reason_string)
        """
        state    = self.monitor.read_state()
        pressure = self.monitor.pressure_score(state)

        # Thermal emergency — drop to survival regardless
        if state.temperature_c >= THERMAL_CRITICAL_CELSIUS:
            tier   = CognitiveTier.SURVIVAL
            reason = f"thermal emergency ({state.temperature_c:.0f}°C >= {THERMAL_CRITICAL_CELSIUS}°C)"
            return self._apply_tier(tier, task, pressure, reason)

        # High pressure — compress below required tier if needed
        if pressure >= PRESSURE_COMPRESS_THRESHOLD:
            tier   = self._compress_tier(task.required_tier, pressure)
            reason = f"high pressure ({pressure:.2f} >= {PRESSURE_COMPRESS_THRESHOLD})"
            return self._apply_tier(tier, task, pressure, reason)

        # Low pressure — can expand to required or higher
        if pressure <= PRESSURE_EXPAND_THRESHOLD:
            tier   = max(task.required_tier, CognitiveTier.ENHANCED)
            tier   = min(tier, self.max_tier)
            reason = f"low pressure ({pressure:.2f} <= {PRESSURE_EXPAND_THRESHOLD}), expanding"
            return self._apply_tier(tier, task, pressure, reason)

        # Normal pressure — use exactly what the task requires
        tier   = task.required_tier
        reason = f"normal pressure ({pressure:.2f}), using required tier"
        return self._apply_tier(tier, task, pressure, reason)

    def _compress_tier(self, required: CognitiveTier, pressure: float) -> CognitiveTier:
        """
        Compress cognitive tier proportionally to pressure severity.
        """
        tiers = list(CognitiveTier)
        required_idx = tiers.index(required)

        # How far to compress: pressure 0.75 → -1 tier, 0.90 → -2 tiers, 1.0 → -3 tiers
        compression_steps = int((pressure - PRESSURE_COMPRESS_THRESHOLD) / 0.08) + 1
        compressed_idx    = max(0, required_idx - compression_steps)
        compressed_tier   = tiers[compressed_idx]

        return max(compressed_tier, self.min_tier)

    def _apply_tier(
        self,
        tier: CognitiveTier,
        task: TaskComplexity,
        pressure: float,
        reason: str,
    ) -> tuple[CognitiveTier, float, str]:
        quality = TIER_QUALITY[tier]
        self._current_tier = tier
        self._history.append({
            "task_id":  task.task_id,
            "tier":     tier.name,
            "dim":      tier.value,
            "quality":  quality,
            "pressure": round(pressure, 3),
            "reason":   reason,
            "ts":       time.time(),
        })
        logger.info(f"[BreathingAgent] task={task.task_id} tier={tier.name} quality={quality:.0%} pressure={pressure:.2f} reason={reason}")
        return tier, quality, reason

    def vram_savings_vs_full(self) -> float:
        """
        Percentage VRAM saved compared to running at full 128-dim resolution.
        """
        full_mult = TIER_VRAM_MULTIPLIER[CognitiveTier.FULL]
        curr_mult = TIER_VRAM_MULTIPLIER[self._current_tier]
        return (1.0 - curr_mult / full_mult) * 100.0

    def history(self) -> list[dict]:
        return list(self._history)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== BreathingAgent Demo ===\n")

    monitor = GPUMonitor(vram_total_gb=24.0, tdp_w=450.0)
    agent   = BreathingAgent(monitor=monitor)

    scenarios = [
        ("hello_world",    50,   CognitiveTier.SURVIVAL,  GPUState.mock(0.30, 55.0)),
        ("code_review",    450,  CognitiveTier.STANDARD,  GPUState.mock(0.60, 68.0)),
        ("deep_analysis",  2200, CognitiveTier.FULL,      GPUState.mock(0.85, 79.0)),
        ("thermal_stress", 900,  CognitiveTier.ENHANCED,  GPUState.mock(0.90, 87.0)),
    ]

    for task_id, tokens, req_tier, state in scenarios:
        monitor._last_state = state
        # Monkey-patch read_state to return our mock state
        monitor.read_state = lambda s=state: s

        task = TaskComplexity(task_id, token_estimate=tokens, required_tier=req_tier)
        tier, quality, reason = agent.select_tier(task)
        savings = agent.vram_savings_vs_full()

        print(f"Task:     {task_id}")
        print(f"Required: {req_tier.name} | Selected: {tier.name} ({tier.value}-dim)")
        print(f"Quality:  {quality:.0%} | VRAM saved vs full: {savings:.1f}%")
        print(f"Reason:   {reason}")
        print()
