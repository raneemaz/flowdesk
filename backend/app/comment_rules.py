"""Who may edit or delete a comment - shared by task comments and
customer-request comments so both follow exactly the same rules.

- Edit: only the comment's author. Nobody can put words in someone
  else's mouth, Owner/Manager included.
- Delete: the author, or an Owner/Manager (moderation - e.g. removing a
  comment posted on the wrong record or containing something sensitive).

Callers check access to the parent record first (the same reach check
as viewing it), so these rules only ever apply to comments the caller
can already see.
"""

import uuid

from app.errors import APIError
from app.models import Membership, MembershipRole

_MODERATOR_ROLES = {MembershipRole.OWNER, MembershipRole.MANAGER}


def require_can_edit(author_membership_id: uuid.UUID | None, actor: Membership) -> None:
    if author_membership_id is None or author_membership_id != actor.id:
        raise APIError("You can only edit your own comments.", status_code=403, code="FORBIDDEN")


def require_can_delete(author_membership_id: uuid.UUID | None, actor: Membership) -> None:
    is_author = author_membership_id is not None and author_membership_id == actor.id
    if not is_author and actor.role not in _MODERATOR_ROLES:
        raise APIError(
            "You can only delete your own comments.", status_code=403, code="FORBIDDEN"
        )


def require_moderator(actor: Membership, what: str) -> None:
    """Owner/Manager-only actions, e.g. permanently deleting a record."""
    if actor.role not in _MODERATOR_ROLES:
        raise APIError(f"Only an owner or manager can {what}.", status_code=403, code="FORBIDDEN")
