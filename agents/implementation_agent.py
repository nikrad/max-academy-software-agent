from agents.base_agent import Agent
from prompts import IMPLEMENTATION_PROMPT


class ImplementationAgent(Agent):
    """
    Agent for implementing the plan.
    """

    def __init__(self, name, client, gen_kwargs=None):
        super().__init__(name, client, IMPLEMENTATION_PROMPT, gen_kwargs)
