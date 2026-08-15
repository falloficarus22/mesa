"""Core meta-agent object and legacy construction helpers.

Meta-agents represent agents that are composed of other agents. The current
experimental rewrite supports overlapping memberships: one agent can belong to
multiple meta-agents at the same time, and canonical membership bookkeeping is
handled by :class:`mesa.experimental.meta_agents.backend.MembershipBackend`.

This module keeps the historical ``MetaAgent`` class and ``create_meta_agent``
function available for existing user code. Their object-level references
(``agent.meta_agents`` and ``agent.meta_agent``) are compatibility mirrors for
older models; new code should use the public ``MetaAgents`` facade and typed
membership backend for authoritative membership state.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from types import MethodType
from typing import Any

from mesa.agent import Agent, AgentSet

_RESERVED_META_ATTRIBUTE_NAMES = {
    "unique_id",
    "model",
    "pos",
    "name",
    "random",
    "rng",
    "meta_agents",
    "meta_agent",
    "_constituting_set",
}


def _unique_id_sort_key(agent: Agent) -> tuple[bool, str]:
    """Return a deterministic, type-stable key for ordering agents by ID."""
    unique_id = getattr(agent, "unique_id", None)
    return (unique_id is not None, "" if unique_id is None else str(unique_id))


def _deduplicate_preserving_order(agents: Iterable[Any]) -> list[Any]:
    """Return unique agents while preserving caller order."""
    return list(dict.fromkeys(agents))


def _normalize_agent_bases(
    mesa_agent_type: type[Agent] | tuple[type[Agent], ...] | None,
) -> tuple[type[Agent], ...]:
    """Normalize user-provided Mesa base classes for dynamic meta-agent classes."""
    if mesa_agent_type is None:
        return (Agent,)
    if isinstance(mesa_agent_type, tuple):
        return mesa_agent_type
    return (mesa_agent_type,)


def _update_primary_meta_agent(agent: Any) -> None:
    """Refresh the legacy ``agent.meta_agent`` pointer from ``agent.meta_agents``."""
    meta_agents = getattr(agent, "meta_agents", set())
    agent.meta_agent = (
        sorted(meta_agents, key=_unique_id_sort_key)[0] if meta_agents else None
    )


def _attach_meta_agent(agent: Any, meta_agent: MetaAgent) -> None:
    """Attach one compatibility mirror membership."""
    if not hasattr(agent, "meta_agents"):
        agent.meta_agents = set()
    agent.meta_agents.add(meta_agent)
    _update_primary_meta_agent(agent)


def _detach_meta_agent(agent: Any, meta_agent: MetaAgent) -> None:
    """Detach one compatibility mirror membership."""
    if not hasattr(agent, "meta_agents"):
        return
    agent.meta_agents.discard(meta_agent)
    _update_primary_meta_agent(agent)


def evaluate_combination(
    candidate_group: tuple[Agent, ...],
    model,
    evaluation_func: Callable[[tuple[Agent, ...]], float] | None,
) -> tuple[tuple[Agent, ...], float] | None:
    """Evaluate a candidate meta-agent group with a user-supplied function."""
    if evaluation_func is None:
        return None
    return candidate_group, evaluation_func(candidate_group)


def find_combinations(
    model,
    group: Iterable,
    size: int | tuple[int, int] = (2, 5),
    evaluation_func: Callable[[tuple[Agent, ...]], float] | None = None,
    filter_func: Callable[
        [list[tuple[tuple[Agent, ...], float]]], list[tuple[tuple[Agent, ...], float]]
    ]
    | None = None,
) -> list[tuple[tuple[Agent, ...], float]]:
    """Find candidate agent groups and score them with ``evaluation_func``.

<<<<<<< HEAD
    The helper is retained for existing examples that discover potential
    meta-agents before creating them. It deliberately does not mutate model or
    membership state.
=======
    Args:
        model: The model instance.
        group: The set of agents to find combinations in.
        size: The size or range of sizes for combinations. Defaults to (2, 5).
        evaluation_func: The function to evaluate combinations. Defaults to None.
        filter_func: Allows the user to specify how agents are filtered to form groups.
          Defaults to None.

    Returns:
        List: The list of valuable combinations, in a tuple first agentset of valuable combination  and then the value of
        the combination.
>>>>>>> origin/main
    """
    if isinstance(size, int):
        size_range = range(size, size + 1)
    else:
        min_size, max_size = size
        size_range = range(min_size, max_size + 1)

    combinations = []
    for candidate_group in itertools.chain.from_iterable(
        itertools.combinations(group, combination_size)
        for combination_size in size_range
    ):
        evaluation_result = evaluate_combination(
            candidate_group, model, evaluation_func
        )
        if evaluation_result is not None:
            _evaluated_group, result = evaluation_result
            if result is not None:
                combinations.append(evaluation_result)

    if combinations and filter_func is not None:
        return filter_func(combinations)
    return combinations


def extract_class(agents_by_type: dict, new_agent_class: object) -> type[Agent] | None:
    """Return the existing model agent class named ``new_agent_class`` if present."""
    agent_type_names = {
        agent_type.__name__: agent_type for agent_type in agents_by_type
    }
    agent_type = agent_type_names.get(new_agent_class)
    if agent_type is None:
        return None
    return type(next(iter(agents_by_type[agent_type])))


def _collect_inferred_attributes(
    agents: Iterable[Any],
    meta_attributes: dict[str, Any] | None,
    assume_constituting_agent_attributes: bool,
) -> dict[str, Any]:
    """Merge explicit and inferred attributes for a new meta-agent instance."""
    resolved_attributes = dict(meta_attributes or {})
    if not assume_constituting_agent_attributes:
        return resolved_attributes

    for agent in agents:
        for name, value in agent.__dict__.items():
            if (
                not callable(value)
                and name not in _RESERVED_META_ATTRIBUTE_NAMES
                and not name.startswith("_")
            ):
                resolved_attributes[name] = value
    return resolved_attributes


def _apply_meta_attributes(
    meta_agent: Any,
    meta_attributes: dict[str, Any] | None,
) -> None:
    """Set resolved meta-agent attributes on an instance."""
    for key, value in (meta_attributes or {}).items():
        setattr(meta_agent, key, value)


def _collect_meta_methods(
    agents: Iterable[Any],
    meta_methods: dict[str, Callable] | None,
    assume_constituting_agent_methods: bool,
) -> dict[str, Callable]:
    """Merge explicit and inferred methods for a meta-agent instance."""
    resolved_meta_methods = dict(meta_methods or {})
    if not assume_constituting_agent_methods:
        return resolved_meta_methods

    for agent_class in dict.fromkeys(type(agent) for agent in agents):
        for name, value in agent_class.__dict__.items():
            if callable(value) and not name.startswith("__"):
                resolved_meta_methods.setdefault(name, value)
    return resolved_meta_methods


def _apply_meta_methods(
    meta_agent: Any,
    meta_methods: dict[str, Callable] | None,
) -> None:
    """Bind resolved meta-agent methods to an instance."""
    for name, method in (meta_methods or {}).items():
        setattr(meta_agent, name, MethodType(method, meta_agent))


def _find_existing_meta_agent(
    agents: Iterable[Any],
    new_agent_class: str,
) -> Any | None:
    """Find a compatible existing meta-agent among legacy mirrors."""
    existing_meta_agents = []
    for agent in agents:
        for meta_agent in sorted(
            getattr(agent, "meta_agents", set()), key=_unique_id_sort_key
        ):
            if (
                meta_agent.__class__.__name__ == new_agent_class
                and meta_agent not in existing_meta_agents
            ):
                existing_meta_agents.append(meta_agent)

    if not existing_meta_agents:
        return None
    return sorted(existing_meta_agents, key=_unique_id_sort_key)[0]


def _build_meta_agent_class(
    new_agent_class: str,
    mesa_agent_type: tuple[type[Agent], ...],
) -> type[Agent]:
    """Create a dynamic meta-agent class with the requested Mesa base types."""
    return type(
        new_agent_class,
        (MetaAgent, *mesa_agent_type),
        {
            "unique_id": None,
            "_constituting_set": None,
        },
    )


def _create_meta_agent_instance(
    model: Any,
    new_agent_class: str,
    agents: Iterable[Any],
    mesa_agent_type: type[Agent] | tuple[type[Agent], ...] | None,
    meta_attributes: dict[str, Any] | None = None,
    meta_methods: dict[str, Callable] | None = None,
    assume_constituting_agent_methods: bool = False,
    assume_constituting_agent_attributes: bool = False,
) -> Any | None:
    """Create or reuse a meta-agent instance without recording backend edges."""
    agents = _deduplicate_preserving_order(agents)
    agent_bases = _normalize_agent_bases(mesa_agent_type)
    resolved_attributes = _collect_inferred_attributes(
        agents,
        meta_attributes,
        assume_constituting_agent_attributes,
    )
    resolved_methods = _collect_meta_methods(
        agents,
        meta_methods,
        assume_constituting_agent_methods,
    )

    meta_agent = _find_existing_meta_agent(agents, new_agent_class)
    if meta_agent is not None:
        _apply_meta_attributes(meta_agent, resolved_attributes)
        _apply_meta_methods(meta_agent, resolved_methods)
        meta_agent.add_constituting_agents(agents)
        return meta_agent

    agent_class = extract_class(model.agents_by_type, new_agent_class)
    if agent_class is None:
        agent_class = _build_meta_agent_class(new_agent_class, agent_bases)

    meta_agent = agent_class(
        model,
        agents,
        initial_attributes=resolved_attributes,
    )
    _apply_meta_attributes(meta_agent, resolved_attributes)
    _apply_meta_methods(meta_agent, resolved_methods)
    return meta_agent


def create_meta_agent(
    model: Any,
    new_agent_class: str,
    agents: Iterable[Any],
    mesa_agent_type: type[Agent] | tuple[type[Agent], ...] | None,
    meta_attributes: dict[str, Any] | None = None,
    meta_methods: dict[str, Callable] | None = None,
    assume_constituting_agent_methods: bool = False,
    assume_constituting_agent_attributes: bool = False,
) -> Any | None:
    """Legacy helper for creating a meta-agent instance.

<<<<<<< HEAD
    This function preserves the historical API and object-level compatibility
    mirrors. It does not own canonical membership bookkeeping; use
    ``MetaAgents.create`` when memberships should be recorded in a
    ``MembershipBackend``.
=======
    Args:
        model: The model instance.
        new_agent_class: The name of the new meta-agent class.
        agents: The agents to be included in the meta-agent.
        mesa_agent_type: The Mesa Agent (sub)class the new meta-agent should
            inherit from. If falsy, defaults to Agent.
        meta_attributes: Attributes to be added to the meta-agent.
        meta_methods: Methods to be added to the meta-agent.
        assume_constituting_agent_methods: Whether to assume methods from
            constituting-agents as meta_agent methods.
        assume_constituting_agent_attributes: Whether to retain attributes
            from constituting-agents.

    Returns:
        MetaAgent instance
>>>>>>> origin/main
    """
    return _create_meta_agent_instance(
        model,
        new_agent_class,
        agents,
        mesa_agent_type,
        meta_attributes=meta_attributes,
        meta_methods=meta_methods,
        assume_constituting_agent_methods=assume_constituting_agent_methods,
        assume_constituting_agent_attributes=assume_constituting_agent_attributes,
    )


class MetaAgent(Agent):
    """An agent composed of other agents.

    ``MetaAgent`` keeps the live object relationship needed by existing models.
    Canonical typed membership storage lives in the backend/facade layer.
    """

    def __init__(
        self,
        model,
        agents: Iterable[Agent] | None = None,
        name: str = "MetaAgent",
        initial_attributes: dict[str, Any] | None = None,
    ):
        """Create a meta-agent from an optional iterable of component agents."""
        if initial_attributes:
            for key, value in initial_attributes.items():
                object.__setattr__(self, key, value)

        super().__init__(model)
        self._constituting_set = AgentSet(agents or [], random=model.random)
        self.name = name

        for agent in self._constituting_set:
            _attach_meta_agent(agent, self)

    def __len__(self) -> int:
        """Return the number of component agents."""
        return len(self._constituting_set)

    def __iter__(self):
        """Iterate over component agents."""
        return iter(self._constituting_set)

    def __contains__(self, agent: Agent) -> bool:
        """Return whether ``agent`` is a component of this meta-agent."""
        return agent in self._constituting_set

    @property
    def agents(self) -> AgentSet:
        """Return the component agents."""
        return self._constituting_set

    @property
    def constituting_agents_by_type(self) -> dict[type, list[Agent]]:
        """Return component agents grouped by their concrete Python type."""
        constituting_agents_by_type = {}
        for agent in self._constituting_set:
            constituting_agents_by_type.setdefault(type(agent), []).append(agent)
        return constituting_agents_by_type

    @property
    def constituting_agent_types(self) -> set[type]:
        """Return the set of component agent types."""
        return {type(agent) for agent in self._constituting_set}

    def get_constituting_agent_instance(self, agent_type) -> Agent:
        """Return the first component agent of ``agent_type``."""
        try:
            return self.constituting_agents_by_type[agent_type][0]
        except KeyError:
            raise ValueError(
                f"No constituting_agent of type {agent_type} found."
            ) from None

    def add_constituting_agents(self, new_agents: Iterable[Agent]) -> None:
        """Add component agents through the model's membership facade."""
        meta_agents_api = getattr(self.model, "meta_agents", None)
        if meta_agents_api is not None:
            for agent in new_agents:
                meta_agents_api.add_member(self, agent)
            return
        self._add_constituting_agents_locally(new_agents)

    def _add_constituting_agents_locally(self, new_agents: Iterable[Agent]) -> None:
        """Update the component and compatibility mirrors without backend mutation."""
        for agent in new_agents:
            self._constituting_set.add(agent)
            _attach_meta_agent(agent, self)

    def remove_constituting_agents(self, remove_agents: Iterable[Agent]) -> None:
        """Remove component agents through the model's membership facade."""
        meta_agents_api = getattr(self.model, "meta_agents", None)
        if meta_agents_api is not None:
            for agent in remove_agents:
                meta_agents_api.remove_member(self, agent)
            return
        self._remove_constituting_agents_locally(remove_agents)

    def _remove_constituting_agents_locally(
        self, remove_agents: Iterable[Agent]
    ) -> None:
        """Update the component and compatibility mirrors without backend mutation."""
        for agent in remove_agents:
            self._constituting_set.discard(agent)
            _detach_meta_agent(agent, self)

    def remove(self) -> None:
        """Remove this meta-agent through the model's membership facade."""
        meta_agents_api = getattr(self.model, "meta_agents", None)
        if meta_agents_api is not None:
            meta_agents_api.dissolve(self)
            return
        self._remove_from_model()

    def _remove_from_model(self) -> None:
        """Remove this agent after backend memberships have been detached."""
        self._remove_constituting_agents_locally(set(self._constituting_set))
        super().remove()

    def step(self) -> None:
        """Default meta-agent behavior."""


__all__ = [
    "MetaAgent",
    "create_meta_agent",
    "evaluate_combination",
    "extract_class",
    "find_combinations",
]
