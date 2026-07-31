"""Tests for the allianceformation meta-agent example."""

from __future__ import annotations

from mesa.examples.advanced.alliance_formation.model import (
    AllianceScenario,
    MultiLevelAllianceModel,
)


def test_alliance_model_records_overlapping_memberships(monkeypatch):
    """The backend should preserve overlap when an agent joins mutiple alliances."""
    model = MultiLevelAllianceModel(
        scenario=AllianceScenario(n=3, mean=0.5, std_dev=0.0, rng=42)
    )
    agents = sorted(model.agents, key=lambda agent: agent.unique_id)
    agent_0, agent_1, agent_2 = agents

    def fake_find_combinations(*args, **kwargs):
        return [
            ((agent_0, agent_1), (1.0, 0.5, 0)),
            ((agent_0, agent_2), (1.0, 0.4, 0)),
        ]

    monkeypatch.setattr(
        "mesa.examples.advanced.alliance_formation.model.find_combinations",
        fake_find_combinations,
    )

    model.step()

    backend = model.membership_backend

    assert len(agent_0.meta_agents) == 2
    assert backend.groups_of(agent_0) == {
        meta.unique_id for meta in agent_0.meta_agents
    }

    expected_triplets = set()
    for agent in agents:
        for meta in agent.meta_agents:
            expected_triplets.add((agent.unique_id, meta.unique_id, "member"))

    assert backend.as_triplets() == expected_triplets
    backend.assert_invariants()


def test_alliance_model_forms_higher_level_alliances():
    """Meta-agents at one level can form an alliance at the next level."""
    model = MultiLevelAllianceModel(
        scenario=AllianceScenario(n=4, mean=0.5, std_dev=0.0, rng=42)
    )

    model.step()
    assert sum(agent.level == 1 for agent in model.agents) == 2

    model.step()
    assert sum(agent.level == 2 for agent in model.agents) == 1
