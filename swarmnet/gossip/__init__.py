"""Gossip protocol package for SwarmNet."""

from swarmnet.gossip.gossip_agent import GossipAgent
from swarmnet.gossip.state_table import GossipStateTable, StateTableEntry

__all__ = ["GossipAgent", "GossipStateTable", "StateTableEntry"]
