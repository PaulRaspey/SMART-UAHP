"""
SMART-UAHP v0.1.0
The Substrate-Agnostic Intelligence Protocol

Layer 2 of the UAHP stack — energy-aware cognitive routing.
"""

from .thermodynamics import (
    EnergyProfile,
    TaskQuote,
    ThermodynamicNegotiator,
    GRID_CARBON_INTENSITY,
    GPU_TDP,
)

from .breathing import (
    CognitiveTier,
    GPUState,
    GPUMonitor,
    TaskComplexity,
    BreathingAgent,
    TIER_QUALITY,
    TIER_VRAM_MULTIPLIER,
)

from .router import (
    RoutingDecision,
    RoutingResult,
    EntropyAwareRouter,
)

__version__ = "0.1.0"
__author__  = "Paul Raspey"

__all__ = [
    "EnergyProfile", "TaskQuote", "ThermodynamicNegotiator",
    "GRID_CARBON_INTENSITY", "GPU_TDP",
    "CognitiveTier", "GPUState", "GPUMonitor",
    "TaskComplexity", "BreathingAgent", "TIER_QUALITY",
    "RoutingDecision", "RoutingResult", "EntropyAwareRouter",
]
