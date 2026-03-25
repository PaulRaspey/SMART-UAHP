"""Agent identity via UAHP v0.5.4."""
# Stub — full implementation delegates to UAHP v0.5.4 identity module.
class AgentIdentity:
    """Wraps UAHP v0.5.4 identity for SMART-UAHP substrate registration."""
    def __init__(self, agent_id: str, substrate: str):
        self.agent_id = agent_id
        self.substrate = substrate

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "substrate": self.substrate}
