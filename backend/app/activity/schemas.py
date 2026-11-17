from pydantic import BaseModel, ConfigDict, Field


class ListActivityQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/activity."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
