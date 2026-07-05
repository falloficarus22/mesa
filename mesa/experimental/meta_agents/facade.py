"""Public facade for the experimental meta-agent membership backend."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from typing import Any

from mesa.agent import Agent

from .backend import MembershipBackend, RelationKey, Triplet
from .meta_agent import create_meta_agent


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


class MetaAgentFacade:
    """Thin public facade over :class:`MembershipBackend`."""

    def __init__(self, model: Any, backend: MembershipBackend | None = None) -> None:
        """Create a facade bound to one model."""
        self.model = model
        self.backend = backend or MembershipBackend()

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

        self.backend.remove_agent(entity)
        self.backend.remove_group(entity)

        for edge in snapshot.memberships:
            group = edge.group
            member = edge.agent
            if hasattr(group, "remove_constituting_agents"):
                group.remove_constituting_agents({member})

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
        agents = list(agents)
        member_relations = list(memberships) if memberships is not None else None
        if member_relations is not None and not agents:
            agents = [member for member, _ in member_relations]

        meta_agent = create_meta_agent(
            self.model,
            new_agent_class,
            agents,
            mesa_agent_type,
            meta_attributes=meta_attributes,
            meta_methods=meta_methods,
            assume_constituting_agent_methods=assume_constituting_agent_methods,
            assume_constituting_agent_attributes=assume_constituting_agent_attributes,
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
        already_linked = bool(self.backend.relations_between(member, group))
        self.backend.add_membership(member, group, relation)

        if not already_linked and hasattr(group, "add_constituting_agents"):
            group.add_constituting_agents({member})

        return self.query_memberships(member)

    def remove_member(
        self,
        group: Hashable,
        member: Hashable,
        relation: RelationKey = "member",
    ) -> MembershipView:
        """Remove one member from one group and keep the object layer in sync."""
        self.backend.remove_membership(member, group, relation)

        if not self.backend.relations_between(member, group) and hasattr(
            group, "remove_constituting_agents"
        ):
            group.remove_constituting_agents({member})

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
        if hasattr(live_entity, "remove"):
            live_entity.remove()
        return snapshot

    def deactivate(self, entity: Hashable) -> MembershipView:
        """Remove an entity from all memberships without deleting the object."""
        return self._detach_entity(entity)
