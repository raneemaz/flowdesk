from pydantic import BaseModel, ConfigDict, Field


class ListNotificationsQuery(BaseModel):
    """Query-string params for GET /organizations/{id}/notifications.
    `unread_only` is a judgment call beyond the spec's own literal
    field list - a direct, low-cost addition (a single extra filter on
    an endpoint that already exists) that doubles as how a caller gets
    their own unread count, via `meta.total` on a request with
    `unread_only=true`, without this task inventing a separate
    dedicated count endpoint the spec's own Section 11.1 outline
    doesn't list."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    unread_only: bool = Field(default=False)
