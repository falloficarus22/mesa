# Meta-agents

Typed overlapping memberships for agents composed of other agents.

Install a facade on the model, then create groups and mutate memberships only
through `model.meta_agents`.

```python
from mesa import Agent, Model
from mesa.meta_agents import MetaAgents

model = Model()
model.meta_agents = MetaAgents(model)

alice = Agent(model)
bob = Agent(model)
team = model.meta_agents.create("Team", [alice, bob], Agent)

model.meta_agents.add_member(team, Agent(model))
model.meta_agents.members_of(team)
model.meta_agents.groups_of(alice)
model.meta_agents.query_memberships(alice)
model.meta_agents.at_level(1, root=team)
model.meta_agents.dissolve(team)
```

```{eval-rst}
.. automodule:: mesa.meta_agents
   :members:
   :imported-members:
```
