"""FD-061: HTTP-layer schema for the conversational assistant's one endpoint."""

from pydantic import BaseModel, ConfigDict, Field


class AskAssistantRequest(BaseModel):
    """Body for POST .../ai-assistant/ask."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
