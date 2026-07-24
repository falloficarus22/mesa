"""Legacy compatibility shim for the experimental meta-agents API."""

from .meta_agents_api import MembershipEdge, MembershipView, MetaAgents

MetaAgentFacade = MetaAgents

__all__ = [
    "MembershipEdge",
    "MembershipView",
    "MetaAgentFacade",
    "MetaAgents",
]
