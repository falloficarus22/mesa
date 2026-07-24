"""Tests for the public meta-agents API."""

from mesa import Agent, Model
from mesa.experimental.meta_agents import (
    MembershipEdge,
    MembershipView,
    MetaAgents,
)


def test_meta_agents_create_records_backend_memberships():
    """Create should return live objects and record backend triplets."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)

    meta_agent = meta_agents.create("Group", [agent_1, agent_2], Agent)

    assert meta_agent is not None
    assert meta_agents.backend.as_triplets() == {
        (agent_1.unique_id, meta_agent.unique_id, "member"),
        (agent_2.unique_id, meta_agent.unique_id, "member"),
    }

    view = meta_agents.query_memberships(agent_1)

    assert isinstance(view, MembershipView)
    assert view.subject is agent_1
    assert view.as_triplets() == {(agent_1, meta_agent, "member")}
    assert len(view) == 1
    assert isinstance(view.memberships[0], MembershipEdge)
    assert view.memberships[0].agent is agent_1
    assert view.memberships[0].group is meta_agent


def test_meta_agents_remove_member_preserves_overlapping_memberships():
    """Removing one relation should keep unrelated memberships intact."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent = Agent(model)
    partner = Agent(model)
    group_one = meta_agents.create("GroupOne", [agent, partner], Agent)
    group_two = meta_agents.create("GroupTwo", [agent], Agent)

    assert group_one is not None
    assert group_two is not None
    assert len(agent.meta_agents) == 2

    view = meta_agents.remove_member(group_one, agent)

    assert view.as_triplets() == {(agent, group_two, "member")}
    assert meta_agents.backend.groups_of(agent) == {group_two.unique_id}
    assert group_one not in agent.meta_agents
    assert group_two in agent.meta_agents
    assert partner.meta_agents == {group_one}


def test_meta_agents_dissolve_cleans_only_target_group():
    """Dissolving a group should keep overlapping memberships on other groups."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)
    agent_3 = Agent(model)
    group_one = meta_agents.create("GroupOne", [agent_1, agent_2], Agent)
    group_two = meta_agents.create("GroupTwo", [agent_1, agent_3], Agent)

    assert group_one is not None
    assert group_two is not None

    snapshot = meta_agents.dissolve(group_one)

    assert snapshot.as_triplets() == {
        (agent_1, group_one, "member"),
        (agent_2, group_one, "member"),
    }
    assert meta_agents.backend.groups_of(agent_1) == {group_two.unique_id}
    assert meta_agents.backend.groups_of(agent_2) == set()
    assert meta_agents.backend.groups_of(agent_3) == {group_two.unique_id}
    assert group_one not in model.agents
    assert group_two in model.agents
    assert group_one not in agent_1.meta_agents
    assert group_two in agent_1.meta_agents


def test_meta_agents_deactivate_detaches_all_memberships_without_removing_entity():
    """Deactivate should clear memberships but keep the entity registered."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)
    group = meta_agents.create("Group", [agent_1, agent_2], Agent)

    assert group is not None

    snapshot = meta_agents.deactivate(agent_1)

    assert snapshot.as_triplets() == {(agent_1, group, "member")}
    assert meta_agents.backend.groups_of(agent_1) == set()
    assert agent_1 in model.agents
    assert group not in agent_1.meta_agents
    assert agent_1.meta_agent is None
    assert group in agent_2.meta_agents
