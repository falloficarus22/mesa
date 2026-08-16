"""Public meta-agents API for the experimental membership backend."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from typing import Any

from mesa.agent import Agent, AgentSet
from mesa.experimental.mesa_signals import ModelSignals

from .backend import MembershipBackend, RelationKey, Triplet
from .meta_agent import (
    MetaAgent,
    _create_meta_agent_instance,
    _deduplicate_preserving_order,
)


@dataclass(frozen=True, slots=True)
class MembershipEdge:
    """A user-facing membership edge with live objects instead of backend ids."""

    agent: Any
    group: Any
    relation: RelationKey


@dataclass(frozen=True, slots=True)
class MembershipView:
    """Read-only snapshot of memberships for one entity."""

    subject: Any
    memberships: tuple[MembershipEdge, ...]

    def __iter__(self):
        """Iterate over the resolved memberships."""
        return iter(self.memberships)

    def __len__(self) -> int:
        """Return the number of resolved memberships."""
        return len(self.memberships)

    @property
    def edges(self) -> tuple[MembershipEdge, ...]:
        """Alias for ``memberships`` to keep the view easy to inspect."""
        return self.memberships

    def as_triplets(self) -> set[tuple[Any, Any, RelationKey]]:
        """Return the memberships as live-object triplets."""
        return {(edge.agent, edge.group, edge.relation) for edge in self.memberships}

    @property
    def agents(self) -> set[Any]:
        """Return all unique agents referenced by the view."""
        return {edge.agent for edge in self.memberships}

    @property
    def groups(self) -> set[Any]:
        """Return all unique groups referenced by the view."""
        return {edge.group for edge in self.memberships}

    @property
    def relations(self) -> set[RelationKey]:
        """Return all unique relation labels referenced by the view."""
        return {edge.relation for edge in self.memberships}


class MetaAgents:
    """Public meta-agents interface over :class:`MembershipBackend`.

    The backend is authoritative for typed memberships. Mutate relationships
    through this facade (``create``, ``add_member``, ``remove_member``,
    ``deactivate``, ``dissolve``). Bound ``MetaAgent`` mutators delegate here.
    Raw ``backend`` writes update the graph only; they do not refresh
    ``MetaAgent.agents`` or ``agent.meta_agents``. Removing an agent from the
    model deactivates its memberships.
    """

    def __init__(self, model: Any, backend: MembershipBackend | None = None) -> None:
        """Create a meta-agents API bound to one model."""
        existing_api = getattr(model, "meta_agents", None)
        if existing_api is not None and existing_api is not self:
            raise RuntimeError("Model already has a different MetaAgents facade")
        if any(isinstance(entity, MetaAgent) for entity in model.agents):
            raise RuntimeError(
                "Cannot install MetaAgents on a model with legacy MetaAgent instances"
            )
        self.model = model
        self.backend = backend or MembershipBackend()
        model.meta_agents = self

        self.model.observe("agents", ModelSignals.AGENT_REMOVED, self._on_agent_removed)

    def _on_agent_removed(self, signal) -> None:
        """Deactivate memberships when a live agent leaves the model."""
        args = signal.additional_kwargs.get("args") or ()
        if not args:
            return
        self.deactivate(args[0])

    def _entity_id(self, entity: Hashable) -> Hashable:
        """Return the backend identity for a live entity or hashable external id."""
        return getattr(entity, "unique_id", entity)

    def _live_entity_lookup(self) -> dict[Hashable, Any]:
        """Build a lookup from backend ids back to live model objects."""
        lookup: dict[Hashable, Any] = {}
        for entity in self.model.agents:
            entity_id = getattr(entity, "unique_id", None)
            if entity_id is not None:
                lookup[entity_id] = entity
        return lookup

    def _resolve_entity(self, entity_id: Hashable) -> Any:
        """Resolve a backend id back to a live object when possible."""
        return self._live_entity_lookup().get(entity_id, entity_id)

    def _resolve_view(
        self, entity: Hashable, triplets: Iterable[Triplet]
    ) -> MembershipView:
        """Convert backend triplets into a user-facing snapshot."""
        lookup = self._live_entity_lookup()
        resolved_edges: list[MembershipEdge] = []
        for agent_id, group_id, relation in sorted(
            triplets,
            key=lambda triplet: (
                str(triplet[0]),
                str(triplet[1]),
                repr(triplet[2]),
            ),
        ):
            resolved_edges.append(
                MembershipEdge(
                    agent=lookup.get(agent_id, agent_id),
                    group=lookup.get(group_id, group_id),
                    relation=relation,
                )
            )

        return MembershipView(
            subject=self._resolve_entity(entity),
            memberships=tuple(resolved_edges),
        )

    def _detach_entity(self, entity: Hashable) -> MembershipView:
        """Remove all incident memberships and update live objects when available."""
        snapshot = self.query_memberships(entity)
        entity_id = self._entity_id(entity)
        live_entity = (
            entity if isinstance(entity, Agent) else self._resolve_entity(entity_id)
        )
        lookup = self._live_entity_lookup()
        if isinstance(live_entity, Agent):
            lookup[entity_id] = live_entity

        self.backend.remove_agent(entity)
        self.backend.remove_group(entity)

        for edge in snapshot.memberships:
            group = (
                edge.group
                if hasattr(edge.group, "_remove_constituting_agents_mirror")
                else lookup.get(self._entity_id(edge.group), edge.group)
            )
            member = (
                edge.agent
                if isinstance(edge.agent, Agent)
                else lookup.get(self._entity_id(edge.agent), edge.agent)
            )
            if isinstance(member, Agent) and hasattr(
                group, "_remove_constituting_agents_mirror"
            ):
                group._remove_constituting_agents_mirror({member})

        return snapshot

    def create(
        self,
        new_agent_class: str,
        agents: Iterable[Any],
        mesa_agent_type: type[Agent] | None,
        meta_attributes: dict[str, Any] | None = None,
        meta_methods: dict[str, Callable] | None = None,
        assume_constituting_agent_methods: bool = False,
        assume_constituting_agent_attributes: bool = False,
        relation: RelationKey = "member",
        memberships: Iterable[tuple[Any, RelationKey]] | None = None,
    ) -> Any | None:
        """Create a meta-agent and record its memberships in the backend."""
        member_relations = list(memberships) if memberships is not None else None
        if member_relations is not None:
            agents = _deduplicate_preserving_order(
                member for member, _ in member_relations
            )
        else:
            agents = _deduplicate_preserving_order(agents)

        meta_agent = _create_meta_agent_instance(
            self.model,
            new_agent_class,
            agents,
            mesa_agent_type,
            meta_attributes=meta_attributes,
            meta_methods=meta_methods,
            assume_constituting_agent_methods=assume_constituting_agent_methods,
            assume_constituting_agent_attributes=assume_constituting_agent_attributes,
            _membership_api=self,
        )

        if meta_agent is None:
            return None

        if member_relations is None:
            member_relations = [(agent, relation) for agent in agents]

        self.backend.bulk_add(
            [(member, meta_agent, rel) for member, rel in member_relations]
        )

        return meta_agent

    def add_member(
        self,
        group: Hashable,
        member: Hashable,
        relation: RelationKey = "member",
    ) -> MembershipView:
        """Add one member to one group and keep the object layer in sync."""
        lookup = self._live_entity_lookup()
        member = lookup.get(self._entity_id(member), member)
        group = lookup.get(self._entity_id(group), group)

        self.backend.add_membership(member, group, relation)

        if (
            isinstance(member, Agent)
            and hasattr(group, "_add_constituting_agents_mirror")
            and member not in group
        ):
            group._add_constituting_agents_mirror({member})

        return self.query_memberships(member)

    def remove_member(
        self,
        group: Hashable,
        member: Hashable,
        relation: RelationKey = "member",
    ) -> MembershipView:
        """Remove one member from one group and keep the object layer in sync."""
        lookup = self._live_entity_lookup()
        member = lookup.get(self._entity_id(member), member)
        group = lookup.get(self._entity_id(group), group)

        self.backend.remove_membership(member, group, relation)

        if (
            not self.backend.relations_between(member, group)
            and isinstance(member, Agent)
            and hasattr(group, "_remove_constituting_agents_mirror")
        ):
            group._remove_constituting_agents_mirror({member})

        return self.query_memberships(member)

    def query_memberships(
        self, entity: Hashable, relation: RelationKey | None = None
    ) -> MembershipView:
        """Return a resolved, read-only snapshot of one entity's memberships."""
        entity_id = self._entity_id(entity)
        triplets = (
            triplet
            for triplet in self.backend.as_triplets()
            if (triplet[0] == entity_id or triplet[1] == entity_id)
            and (relation is None or triplet[2] == relation)
        )
        return self._resolve_view(entity_id, triplets)

    def dissolve(self, entity: Hashable) -> MembershipView:
        """Remove an entity's memberships and delete it from the model when possible."""
        snapshot = self._detach_entity(entity)
        live_entity = self._resolve_entity(self._entity_id(entity))
        if hasattr(live_entity, "_remove_from_model"):
            live_entity._remove_from_model()
        elif hasattr(live_entity, "remove"):
            live_entity.remove()
        return snapshot

    def deactivate(self, entity: Hashable) -> MembershipView:
        """Remove an entity from all memberships without deleting the object."""
        return self._detach_entity(entity)

    def at_level(
        self,
        level: int,
        *,
        root: Hashable,
        relation: RelationKey | None = "member",
    ) -> AgentSet:
        """Return agents at a containment depth below ``root``.

        Levels are structural shortest-path distances through membership edges,
        not a persistent ``agent.level`` property. ``root`` is level ``0``; its
        direct members are level ``1``. When an agent is reachable by more than
        one path, it appears only at its shallowest depth from ``root``.

        Parameters
        ----------
        level : int
            Non-negative containment depth relative to ``root``.
        root : Hashable
            Hierarchy root (live agent or backend id). Must be registered on
            this façade's model.
        relation : RelationKey or None, default ``"member"``
            Membership relation to traverse. ``None`` includes all relations.

        Returns:
        -------
        AgentSet
            Live agents at the requested level (empty if none).

        Raises:
        ------
        ValueError
            If ``level`` is negative or ``root`` is not in the model.

        Examples:
        --------
        >>> model.meta_agents.at_level(4, root=world)
        """
        if level < 0:
            raise ValueError(f"level must be non-negative, got {level}")

        lookup = self._live_entity_lookup()
        root_id = self._entity_id(root)
        if root_id not in lookup:
            raise ValueError(f"root {root!r} is not registered in the model")

        if level == 0:
            return AgentSet([lookup[root_id]], random=self.model.random)

        # BFS downward: group -> members. First visit is nearest depth.
        visited: set[Hashable] = {root_id}
        queue: deque[tuple[Hashable, int]] = deque([(root_id, 0)])
        at_depth: list[Any] = []

        while queue:
            group_id, depth = queue.popleft()
            if depth >= level:
                continue
            member_ids = sorted(
                self.backend.agents_of(group_id, relation=relation),
                key=str,
            )
            for member_id in member_ids:
                if member_id in visited:
                    continue
                visited.add(member_id)
                next_depth = depth + 1
                if next_depth == level:
                    entity = lookup.get(member_id)
                    if entity is not None:
                        at_depth.append(entity)
                elif next_depth < level:
                    queue.append((member_id, next_depth))

        return AgentSet(at_depth, random=self.model.random)


__all__ = [
    "MembershipEdge",
    "MembershipView",
    "MetaAgents",
]
