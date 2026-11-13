from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateOrganizationRequest(BaseModel):
    # Makes "no escalation via extra fields" (role, user_id, organization_id,
    # slug) an explicit, enforced 422 rather than relying on pydantic's
    # default silent-drop behavior for fields we didn't declare.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    logo: str | None = Field(default=None, max_length=2048)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, max_length=64)
    date_format: str | None = Field(default=None, max_length=32)
