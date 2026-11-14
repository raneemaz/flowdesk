from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import MembershipRole


class CreateInvitationRequest(BaseModel):
    # extra="forbid": no smuggling e.g. organization_id/status/token
    # through the body - same defense-in-depth as CreateOrganizationRequest.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # Typed directly as the enum - pydantic validates the string against
    # MembershipRole's own values, so "owner"/"manager"/.../"customer_support"
    # are the only accepted spellings; anything else is a 422, not a
    # silently-ignored or coerced value.
    role: MembershipRole


class AcceptInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
