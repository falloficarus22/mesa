"""Tests for the public meta-agents API."""

import pytest

from mesa import Agent, Model
from mesa.agent import AgentSet
from mesa.experimental.meta_agents import (
    MembershipEdge,
    MembershipView,
    MetaAgents,
)
from mesa.experimental.meta_agents.meta_agent import MetaAgent, create_meta_agent


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


def test_meta_agents_installs_one_authoritative_facade_per_model():
    """A model can have only one facade and rejects pre-existing legacy groups."""
    model = Model()
    meta_agents = MetaAgents(model)

    assert model.meta_agents is meta_agents
    with pytest.raises(RuntimeError, match="different MetaAgents facade"):
        MetaAgents(model)

    legacy_model = Model()
    MetaAgent(legacy_model)
    with pytest.raises(RuntimeError, match="legacy MetaAgent instances"):
        MetaAgents(legacy_model)


def test_legacy_group_creation_is_rejected_when_facade_is_installed():
    """Raw legacy construction cannot create an untracked group beside a facade."""
    model = Model()
    MetaAgents(model)
    member = Agent(model)

    with pytest.raises(RuntimeError, match=r"model\.meta_agents\.create"):
        MetaAgent(model, [member])
    with pytest.raises(RuntimeError, match=r"model\.meta_agents\.create"):
        create_meta_agent(model, "Group", [member], Agent)


def test_bound_legacy_mutators_keep_backend_and_mirrors_in_sync():
    """Legacy mutations on facade-created groups are routed through the backend."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent_1 = Agent(model)
    agent_2 = Agent(model)
    group = meta_agents.create("Group", [agent_1], Agent)

    assert group is not None
    group.add_constituting_agents([agent_2])
    assert meta_agents.backend.as_triplets() == {
        (agent_1.unique_id, group.unique_id, "member"),
        (agent_2.unique_id, group.unique_id, "member"),
    }
    assert agent_2 in group
    assert group in agent_2.meta_agents

    group.remove_constituting_agents([agent_1])
    assert meta_agents.backend.as_triplets() == {
        (agent_2.unique_id, group.unique_id, "member")
    }
    assert agent_1 not in group
    assert group not in agent_1.meta_agents

    group.remove()
    assert meta_agents.backend.as_triplets() == set()
    assert group not in model.agents
    assert group not in agent_2.meta_agents


def test_dissolve_skips_mirror_updates_for_already_removed_members():
    """Dissolve handles backend IDs whose live agents were deregistered first."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent = Agent(model)
    group = meta_agents.create("Group", [agent], Agent)

    assert group is not None
    agent.remove()
    assert meta_agents.backend.as_triplets() == set()
    assert agent not in group
    group.remove()

    assert meta_agents.backend.as_triplets() == set()
    assert group not in model.agents


def test_create_memberships_is_authoritative_over_agents_list():
    """When memberships= is given, it replaces the agents list for both layers."""
    model = Model()
    meta_agents = MetaAgents(model)
    listed = Agent(model)
    actual = Agent(model)
    group = meta_agents.create(
        "Group",
        [listed],
        Agent,
        memberships=[(actual, "member")],
    )
    assert group is not None
    assert listed not in group
    assert actual in group
    assert group in actual.meta_agents
    assert group not in getattr(listed, "meta_agents", set())
    assert meta_agents.backend.as_triplets() == {
        (actual.unique_id, group.unique_id, "member")
    }


def test_member_remove_deactivates_memberships_and_mirrors():
    """Removing a member from the model deactivates its memberships and mirrors."""
    model = Model()
    meta_agents = MetaAgents(model)
    member = Agent(model)
    other = Agent(model)
    group = meta_agents.create("Group", [member, other], Agent)
    assert group is not None
    member.remove()
    assert meta_agents.backend.groups_of(member) == set()
    assert member not in group
    assert group not in getattr(member, "meta_agents", set())
    assert other in group
    assert group in other.meta_agents
    assert member not in model.agents
    assert group in model.agents


def test_meta_agent_remove_still_dissolves_after_agent_removed_signal():
    """Bound group.remove() still dissolves after AGENT_REMOVED fires."""
    model = Model()
    meta_agents = MetaAgents(model)
    member = Agent(model)
    group = meta_agents.create("Group", [member], Agent)
    assert group is not None
    group.remove()
    assert meta_agents.backend.as_triplets() == set()
    assert group not in model.agents
    assert group not in member.meta_agents


def test_add_member_heals_mirror_after_backend_only_edge():
    """A second typed edge via the facade heals the live constituting set."""
    model = Model()
    meta_agents = MetaAgents(model)
    member = Agent(model)
    group = meta_agents.create("Group", [], Agent)
    assert group is not None
    meta_agents.backend.add_membership(member, group, "ally")
    assert member not in group
    meta_agents.add_member(group, member, relation="member")
    assert meta_agents.backend.relations_between(member, group) == {"ally", "member"}
    assert member in group
    assert group in member.meta_agents


def test_add_and_remove_member_by_unique_id_updates_mirrors():
    """add_member/remove_member resolve unique_ids to live objects for mirrors."""
    model = Model()
    meta_agents = MetaAgents(model)
    member = Agent(model)
    group = meta_agents.create("Group", [], Agent)
    assert group is not None
    meta_agents.add_member(group, member.unique_id)
    assert member in group
    assert group in member.meta_agents
    assert meta_agents.backend.groups_of(member) == {group.unique_id}
    meta_agents.remove_member(group.unique_id, member.unique_id)
    assert member not in group
    assert group not in member.meta_agents
    assert meta_agents.backend.groups_of(member) == set()


def test_legacy_remove_default_relation_keeps_other_relation_and_mirror():
    """Legacy removal affects only the default relation, not typed memberships."""
    model = Model()
    meta_agents = MetaAgents(model)
    agent = Agent(model)
    group = meta_agents.create("Group", [], Agent)

    assert group is not None
    meta_agents.add_member(group, agent, relation="ally")
    group.add_constituting_agents([agent])
    group.remove_constituting_agents([agent])

    assert meta_agents.backend.as_triplets() == {
        (agent.unique_id, group.unique_id, "ally")
    }
    assert agent in group
    assert group in agent.meta_agents


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


def _four_level_hierarchy():
    """Build world -> region -> city -> household -> person hierarchy."""
    model = Model()
    meta_agents = MetaAgents(model)
    model.meta_agents = meta_agents

    person_a = Agent(model)
    person_b = Agent(model)
    person_c = Agent(model)
    household = meta_agents.create("Household", [person_a, person_b], Agent)
    city = meta_agents.create("City", [household, person_c], Agent)
    region = meta_agents.create("Region", [city], Agent)
    world = meta_agents.create("World", [region], Agent)

    return (
        model,
        meta_agents,
        world,
        region,
        city,
        household,
        person_a,
        person_b,
        person_c,
    )


def test_at_level_four_level_hierarchy():
    """Each containment depth from root returns the expected AgentSet."""
    (
        _model,
        meta_agents,
        world,
        region,
        city,
        household,
        person_a,
        person_b,
        person_c,
    ) = _four_level_hierarchy()

    level0 = meta_agents.at_level(0, root=world)
    assert isinstance(level0, AgentSet)
    assert set(level0) == {world}

    assert set(meta_agents.at_level(1, root=world)) == {region}
    assert set(meta_agents.at_level(2, root=world)) == {city}
    assert set(meta_agents.at_level(3, root=world)) == {household, person_c}
    assert set(meta_agents.at_level(4, root=world)) == {person_a, person_b}


def test_at_level_siblings_and_agentset_ops():
    """Siblings share a level and results support AgentSet selection."""
    _, meta_agents, world, _, _, _, person_a, person_b, _ = _four_level_hierarchy()

    level4 = meta_agents.at_level(4, root=world)
    assert set(level4) == {person_a, person_b}
    selected = level4.select(lambda a: a is person_a)
    assert set(selected) == {person_a}


def test_at_level_order_is_deterministic():
    """Same-level agents keep stable order (sorted member ids per group)."""
    model = Model()
    meta_agents = MetaAgents(model)
    root = Agent(model)
    # Fill so next ids are 11 and 2: str sort is "11" < "2", unlike int order.
    fillers = [Agent(model) for _ in range(9)]  # ids 2..10
    agent_11 = Agent(model)  # id 11
    agent_2 = fillers[0]  # id 2

    meta_agents.backend.add_membership(agent_11, root, "member")
    meta_agents.backend.add_membership(agent_2, root, "member")

    # Unsorted set iteration follows int hash order (2 then 11).
    # String sort requires "11" before "2".
    assert str(agent_11.unique_id) < str(agent_2.unique_id)
    assert agent_2.unique_id < agent_11.unique_id
    assert list(meta_agents.at_level(1, root=root)) == [agent_11, agent_2]
    assert list(meta_agents.at_level(1, root=root)) == list(
        meta_agents.at_level(1, root=root)
    )


def test_at_level_default_relation_and_explicit_relation():
    """Default ignores non-member edges; explicit relation includes them."""
    model = Model()
    meta_agents = MetaAgents(model)
    root = Agent(model)
    member = Agent(model)
    ally = Agent(model)
    meta_agents.backend.add_membership(member, root, "member")
    meta_agents.backend.add_membership(ally, root, "ally")

    assert set(meta_agents.at_level(1, root=root)) == {member}
    assert set(meta_agents.at_level(1, root=root, relation="ally")) == {ally}
    assert set(meta_agents.at_level(1, root=root, relation=None)) == {member, ally}


def test_at_level_overlapping_paths_use_nearest_depth():
    """An agent on multiple paths appears only at its shallowest level."""
    model = Model()
    meta_agents = MetaAgents(model)
    root = Agent(model)
    mid = Agent(model)
    leaf = Agent(model)
    # root --member--> leaf (depth 1)
    # root --member--> mid --member--> leaf (depth 2)
    meta_agents.backend.add_membership(leaf, root, "member")
    meta_agents.backend.add_membership(mid, root, "member")
    meta_agents.backend.add_membership(leaf, mid, "member")

    assert set(meta_agents.at_level(1, root=root)) == {leaf, mid}
    assert set(meta_agents.at_level(2, root=root)) == set()


def test_at_level_empty_and_validation():
    """Absent levels are empty; invalid level/root raise ValueError."""
    model = Model()
    meta_agents = MetaAgents(model)
    root = Agent(model)
    outsider = object()

    assert len(meta_agents.at_level(3, root=root)) == 0

    with pytest.raises(ValueError, match="non-negative"):
        meta_agents.at_level(-1, root=root)

    with pytest.raises(ValueError, match="not registered"):
        meta_agents.at_level(0, root=outsider)


def test_at_level_cyclic_membership_terminates():
    """Cyclic membership graphs must not loop indefinitely."""
    model = Model()
    meta_agents = MetaAgents(model)
    a = Agent(model)
    b = Agent(model)
    meta_agents.backend.add_membership(b, a, "member")
    meta_agents.backend.add_membership(a, b, "member")

    assert set(meta_agents.at_level(0, root=a)) == {a}
    assert set(meta_agents.at_level(1, root=a)) == {b}
    assert set(meta_agents.at_level(2, root=a)) == set()
