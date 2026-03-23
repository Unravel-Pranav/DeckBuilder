import sys
import json
import re
from typing import Any, Dict, List, Optional, Mapping, cast
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from hello.ml.agents.base_agent import BaseAgent
from hello.ml.utils.config_loader import load_agent_prompts
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.ml.logger import GLOBAL_LOGGER as logger


# OpenAI/Chat Completions structured output shape:
# {"type":"json_schema","json_schema":{"name":...,"schema":...,"strict":true}}
ai_response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "generated_titles_response",
        "schema": {
            "type": "object",
            "properties": {
                "1": {"type": "string"},
                "2": {"type": "string"},
                "3": {"type": "string"},
            },
            "required": ["1", "2", "3"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

class TitleGenerationAgent(BaseAgent):
    """Title generation agent that generates a title for a given list of summaries."""
    AGENT_CONFIG_KEY = "title_generation_agent"

    def __init__(self, state: Dict[str, Any]) -> None:
        
        # Load all prompts for this agent
        self.agent_prompts = load_agent_prompts("title_generation_agent")
        self.system_prompt = self.agent_prompts.get("system_prompt", "")
        self.user_prompt_template = self.agent_prompts.get("user_prompt", "")
        self.response_format = ai_response_format

        super().__init__(state)

    def _initialize_agent_specific_attributes(self) -> None:
        """Initialize agent-specific attributes from state."""
        list_of_summaries = self.state.get("summaries", [])
        self.summaries = self._preprocess_summary_results(list_of_summaries)

    def _get_agent_goal(self) -> str:
        """Default implementation - not used in this agent."""
        return "This agent generates a title for a given list of summaries."

    def _create_agent(self):
        """Create ReAct agent with dynamic prompting."""
        # Bind response_format so providers that support it (OpenAI / WSO2 OpenAI gateway)
        # will return strict JSON matching our schema.
        model = getattr(self.model, "bind", None)
        bound_model = self.model.bind(response_format=self.response_format) if callable(model) else self.model
        return create_react_agent(
            model=bound_model,
            tools=[],  # No tools needed for direct summarization
            prompt=self._dynamic_prompt,
        )

    def _dynamic_prompt(self, state: Dict[str, Any], config: Optional[RunnableConfig] = None) -> List[BaseMessage]:
        """Dynamic prompt that combines system and user prompts for title generation."""
        cfg = (config or {}).get("configurable", {})
        summaries = cfg.get("summaries", self.summaries)

        # Provider-agnostic enforcement: even if the underlying model doesn't support
        # `response_format`, we still instruct it to output strict JSON only.
        json_output_instructions = (
            "OUTPUT REQUIREMENTS (STRICT):\n"
            "- Return ONLY valid JSON (no markdown, no code fences, no extra text).\n"
            '- JSON must be an object with EXACT keys "1", "2", "3" and string values.\n'
            '- Do not include additional keys.\n'
            "- Titles must follow the title rules above.\n"
            "\n"
            "JSON SCHEMA:\n"
            f"{json.dumps(self.response_format.get('json_schema', {}).get('schema', {}), ensure_ascii=False)}"
        )

        user_content = self.user_prompt_template.format(
            summaries=summaries
        )
        user_content = f"{user_content}\n\n{json_output_instructions}"
        messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt), HumanMessage(content=user_content)]
        return messages

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        """Best-effort extraction of a JSON object from model output."""
        stripped = text.strip()

        # Prefer fenced JSON blocks if present
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, flags=re.IGNORECASE)
        if fenced:
            candidate = fenced.group(1).strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

        # Otherwise, take the outermost {...} span
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]

        return stripped

    @classmethod
    def _parse_and_validate_titles(cls, raw_text: str) -> Dict[str, str]:
        """Parse and validate the title JSON: must be {"1": str, "2": str, "3": str}."""
        candidate = cls._extract_first_json_object(raw_text)
        parsed = json.loads(candidate)

        if not isinstance(parsed, Mapping):
            raise ValueError("TitleGenerationAgent output is not a JSON object")

        parsed_map = cast(Mapping[str, Any], parsed)
        required_keys = {"1", "2", "3"}
        keys = set(parsed_map.keys())
        if keys != required_keys:
            raise ValueError(f"TitleGenerationAgent JSON keys must be exactly {sorted(required_keys)}; got {sorted(keys)}")

        normalized: Dict[str, str] = {}
        for k in ("1", "2", "3"):
            v = parsed_map.get(k)
            if not isinstance(v, str):
                raise ValueError(f"TitleGenerationAgent value for key '{k}' must be a string")
            v = v.strip()
            if not v:
                raise ValueError(f"TitleGenerationAgent value for key '{k}' must be non-empty")
            normalized[k] = v

        return normalized
    
    def generate_title(self) -> BaseMessage:
        """Generate a title for a given list of summaries."""
        try:
            logger.info("Starting TitleGenerationAgent title generation process")

            # Prepare state and config for the agent
            state = {}

            config = {
                "configurable": {
                    "summaries": self.summaries
                }
            }

            # Invoke the dynamic ReAct agent with automatic fallback
            result = self.invoke_with_fallback(state, config=config)

            # Extract the agent's output from the last message
            agent_output = result["messages"][-1].content

            # Enforce the structured response format expected by the API layer
            titles = self._parse_and_validate_titles(agent_output)
            agent_output = json.dumps(titles, ensure_ascii=False)
            logger.info(
                f"TitleGenerationAgent completed title generation: {len(agent_output)} characters"
            )

            # Return as BaseMessage-compatible object
            return HumanMessage(content=agent_output)

        except Exception as e:
            MultiAgentWorkflowException.log_exception(e, "title_generation")
            raise MultiAgentWorkflowException(
                "Error in title_generation node ", sys.exc_info()
            )

if __name__ == "__main__":
    state = {
        "summaries": [
            "The market is doing well.",
            "The market is doing poorly.",
            "The market is doing well.",
        ]
    }
    agent = TitleGenerationAgent(state)
    title = agent.generate_title()
    print(title)