"""Tests for the public meta-agent facade."""

from mesa import Agent, Model
from mesa.experimental.meta_agents import (
    MembershipEdge,
    MembershipView,
    MetaAgentFacade,
)


def test_facade_create_records_backend_memberships():
    """Create should return live objects and record backend triplets."""
    model = Model()
    facade = MetaAgentFacade(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)

    meta_agent = facade.create("Group", [agent_1, agent_2], Agent)

    assert meta_agent is not None
    assert facade.backend.as_triplets() == {
        (agent_1.unique_id, meta_agent.unique_id, "member"),
        (agent_2.unique_id, meta_agent.unique_id, "member"),
    }

    view = facade.query_memberships(agent_1)

    assert isinstance(view, MembershipView)
    assert view.subject is agent_1
    assert view.as_triplets() == {(agent_1, meta_agent, "member")}
    assert len(view) == 1
    assert isinstance(view.memberships[0], MembershipEdge)
    assert view.memberships[0].agent is agent_1
    assert view.memberships[0].group is meta_agent


def test_facade_remove_member_preserves_overlapping_memberships():
    """Removing one relation should keep unrelated memberships intact."""
    model = Model()
    facade = MetaAgentFacade(model)
    agent = Agent(model)
    partner = Agent(model)
    group_one = facade.create("GroupOne", [agent, partner], Agent)
    group_two = facade.create("GroupTwo", [agent], Agent)

    assert group_one is not None
    assert group_two is not None
    assert len(agent.meta_agents) == 2

    view = facade.remove_member(group_one, agent)

    assert view.as_triplets() == {(agent, group_two, "member")}
    assert facade.backend.groups_of(agent) == {group_two.unique_id}
    assert group_one not in agent.meta_agents
    assert group_two in agent.meta_agents
    assert partner.meta_agents == {group_one}


def test_facade_dissolve_cleans_only_target_group():
    """Dissolving a group should keep overlapping memberships on other groups."""
    model = Model()
    facade = MetaAgentFacade(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)
    agent_3 = Agent(model)
    group_one = facade.create("GroupOne", [agent_1, agent_2], Agent)
    group_two = facade.create("GroupTwo", [agent_1, agent_3], Agent)

    assert group_one is not None
    assert group_two is not None

    snapshot = facade.dissolve(group_one)

    assert snapshot.as_triplets() == {
        (agent_1, group_one, "member"),
        (agent_2, group_one, "member"),
    }
    assert facade.backend.groups_of(agent_1) == {group_two.unique_id}
    assert facade.backend.groups_of(agent_2) == set()
    assert facade.backend.groups_of(agent_3) == {group_two.unique_id}
    assert group_one not in model.agents
    assert group_two in model.agents
    assert group_one not in agent_1.meta_agents
    assert group_two in agent_1.meta_agents


def test_facade_deactivate_detaches_all_memberships_without_removing_entity():
    """Deactivate should clear memberships but keep the entity registered."""
    model = Model()
    facade = MetaAgentFacade(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)
    group = facade.create("Group", [agent_1, agent_2], Agent)

    assert group is not None

    snapshot = facade.deactivate(agent_1)

    assert snapshot.as_triplets() == {(agent_1, group, "member")}
    assert facade.backend.groups_of(agent_1) == set()
    assert agent_1 in model.agents
    assert group not in agent_1.meta_agents
    assert agent_1.meta_agent is None
    assert group in agent_2.meta_agents
