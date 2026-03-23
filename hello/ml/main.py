from fastapi import FastAPI, HTTPException
from langchain_core.messages import BaseMessage
import yaml
import os

from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.ml.agents.session_summary_agent import SessionSummaryAgent
from hello.services.config import settings

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/sessions")
def get_available_sessions():
    """
    Get list of available session types from prompts.yaml.

    Returns:
        List of available session types with their metadata
    """
    try:
        prompt_version = settings.LLM_PROMPT_VERSION
        config_path = os.path.join(
            os.path.dirname(__file__), "config", f"prompts_{prompt_version}.yaml"
        )
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        sessions = {}
        for session_type, session_data in config["prompts"].items():
            sessions[session_type] = {
                "name": session_data["name"],
                "description": session_data["description"],
                "endpoint": session_data["endpoint"],
            }

        return {"sessions": sessions}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="prompts.yaml file not found")
    except Exception as e:
        logger.error(f"Error loading sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading sessions: {str(e)}")


@app.post("/analyze")
def analyze_data(session_type: str, input_data: str):
    """
    Dynamic analysis endpoint that takes session type and input data.
    Uses prompts from prompts.yaml file.

    Args:
        session_type: Type of analysis session (market, asking_rent, vacancy, construction, leasing, net_absorption)
        input_data: The input data to analyze

    Returns:
        Analysis result from the session summary agent
    """
    try:
        # Use the session summary agent to process the data
        session_agent = SessionSummaryAgent(
            {
                "session_type": session_type,
                "input_data": input_data,
            }
        )
        result: BaseMessage = session_agent.generate_summary()

        # Format the response for better readability
        formatted_result = result.content.strip()  # type: ignore
        formatted_result = "\n".join(
            line.strip() for line in formatted_result.split("\n") if line.strip()
        )

        logger.info(f"Analysis completed for session type: {session_type}")
        return {
            "session_type": session_type,
            "result": formatted_result,
            "status": "success",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.post("/generic")
def get_generic_analysis(prompt: str, input_data: str):
    """
    Generic agent endpoint for any custom analysis using SessionSummaryAgent.

    Args:
        prompt: The prompt template to use
        input_data: The input data to process

    Returns:
        Analysis result from the session summary agent
    """
    try:
        from langchain_core.prompts import PromptTemplate
        from hello.ml.utils.model_loader import ModelLoader

        # Create the prompt template
        prompt_template = PromptTemplate(
            template=prompt,
            input_variables=["input_json"],
        )

        # Load the model
        model_loader = ModelLoader()
        model = model_loader.load_model()

        # Run the chain
        chain = prompt_template | model
        result = chain.invoke(
            {
                "input_json": input_data,
            }
        )

        # Format the response for better readability
        formatted_result = result.content.strip()  # type: ignore
        formatted_result = "\n".join(
            line.strip() for line in formatted_result.split("\n") if line.strip()
        )

        return {"result": formatted_result, "status": "success"}

    except Exception as e:
        logger.error(f"Error in generic analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Generic analysis error: {str(e)}")
