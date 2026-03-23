import sys
from pathlib import Path
import yaml

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.exception.custom_exception import MultiAgentWorkflowException
from hello.services.config import settings

from fastapi import HTTPException


def load_config(config_path: Path | None = None) -> dict:
    """
    Loads the configuration from the given path.
    """
    try:
        # If not, use the default path
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"

        # Check if the config path exists
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Load the config
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        # Return the config
        return config
    except Exception as e:
        MultiAgentWorkflowException.log_exception(e, "load_config")
        raise MultiAgentWorkflowException("Error in load_config", sys.exc_info())


def load_prompt_from_config(session_type: str) -> tuple[str, str]:
    """
    Load prompt from prompts.yaml file based on session type.

    Args:
        session_type: Type of session (market, asking_rent, vacancy, etc.)

    Returns:
        tuple[str, str]: The prompt template and few_shot_examples

    Raises:
        HTTPException: If prompt not found or config error
    """
    try:
        prompt_version = settings.LLM_PROMPT_VERSION
        logger.info(f"Prompt version: {prompt_version}")

        config_path = (
            Path(__file__).parent.parent / "config" / f"prompts_{prompt_version}.yaml"
        )
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        logger.info(f"Loading prompt from: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Normalize session type to match YAML keys
        session_type = session_type.lower()
        session_type = session_type.replace(" ", "_")

        # Load system prompt from session-specific section
        system_prompt = config["prompts"][session_type]["system_prompt"]

        # Load common user_prompt template (shared across all sections)
        common_user_prompt = config.get("common", {}).get("user_prompt", "")

        # Load session-specific few_shot_examples
        few_shot_examples = config["prompts"][session_type]["few_shot_examples"]

        # Combine system prompt with common user prompt
        #prompt_template = system_prompt + common_user_prompt

        # Just pass the system prompt as it is
        prompt_template = system_prompt



        logger.info(f"Loaded prompt for session type: {session_type}")
        return prompt_template, few_shot_examples

    except KeyError as e:
        logger.error(f"Session type '{session_type}' not found in {config_path} file: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Session type '{session_type}' not found in {config_path} file",
        )
    except FileNotFoundError:
        logger.error(f"{config_path} file not found")
        raise HTTPException(status_code=404, detail=f"{config_path} file not found")
    except Exception as e:
        logger.error(f"Error loading prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading prompt: {str(e)}")


def load_agent_goal(session_type: str, agent_type: str) -> str:
    """Load agent-specific goal from configuration.

    NOTE: This function is deprecated in favor of load_agent_prompts() which uses agents_prompt_v4_gpt.yaml.
    It's kept for backward compatibility but returns generic goals based on agent type.

    Args:
        session_type (str): The session type (e.g., "vacancy", "leasing")
        agent_type (str): The agent type (e.g., "unit_check", "data_check", "validation")

    Returns:
        str: The agent goal/rules text
    """
    # Return generic goals based on agent type since v3 prompts don't have agent_goals sections
    # and the system now uses agents_prompt_v4_gpt.yaml for detailed agent configuration

    agent_goals = {
        "unit_check": "Validate numeric formatting, units, and professional presentation standards in generated summaries.",
        "data_check": "Ensure data accuracy and consistency between original input data and generated summaries.",
        "validation": "Perform comprehensive quality assessment and provide final approval or improvement recommendations.",
        "summary": "Generate comprehensive, professional summaries following the specified format and requirements."
    }

    goal = agent_goals.get(agent_type, f"Perform {agent_type} tasks according to specified requirements.")

    logger.info(f"Using generic agent goal for {session_type}:{agent_type} ({len(goal)} characters)")
    return goal


def load_agent_prompts(agent_name: str) -> dict:
    """
    Load agent prompts from agents_prompt_v4_gpt.yaml file based on agent name.

    Args:
        agent_name: Name of the agent (e.g., 'session_summary_agent', 'data_check_agent', etc.)

    Returns:
        dict: Dictionary containing the agent's prompt configurations

    Raises:
        MultiAgentWorkflowException: If agent not found or config error
    """
    try:
        # Get the path to the agents_prompt_v4_gpt.yaml file
        config_path = Path(__file__).parent.parent / "config" / "agents_prompt_v4_common.yaml"
        

        # Check if the config path exists
        if not config_path.exists():
            raise FileNotFoundError(f"Agents prompt file not found: {config_path}")

        logger.info(f"Loading agent prompts from: {config_path}")

        # Load the YAML file
        with open(config_path, "r", encoding="utf-8") as f:
            agents_data = yaml.safe_load(f) or {}

        # Check if the agent exists in the config
        if agent_name not in agents_data:
            available_agents = list(agents_data.keys())
            logger.error(f"Agent '{agent_name}' not found in agents_prompt_v4_common.yaml")
            logger.error(f"Available agents: {available_agents}")
            raise KeyError(
                f"Agent '{agent_name}' not found. Available agents: {available_agents}"
            )

        # Get the agent's prompt configuration
        agent_prompts = agents_data[agent_name]

        logger.info(f"Successfully loaded prompts for agent: {agent_name}")
        logger.info(f"Available prompt keys: {list(agent_prompts.keys())}")

        return agent_prompts

    except FileNotFoundError as e:
        logger.error(f"Agents prompt file not found: {e}")
        MultiAgentWorkflowException.log_exception(e, "load_agent_prompts")
        raise MultiAgentWorkflowException(
            f"Agents prompt file not found: {e}", sys.exc_info()
        )

    except KeyError as e:
        logger.error(f"Agent not found: {e}")
        MultiAgentWorkflowException.log_exception(e, "load_agent_prompts")
        raise MultiAgentWorkflowException(f"Agent not found: {e}", sys.exc_info())

    except Exception as e:
        logger.error(f"Error loading agent prompts: {str(e)}")
        MultiAgentWorkflowException.log_exception(e, "load_agent_prompts")
        raise MultiAgentWorkflowException(
            f"Error loading agent prompts: {str(e)}", sys.exc_info()
        )


if __name__ == "__main__":
    agent_prompts = load_agent_prompts("session_summary_agent")
    logger.info(agent_prompts)
