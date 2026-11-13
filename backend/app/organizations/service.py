import re
import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Membership, MembershipRole, Organization, User

_MAX_SLUG_ATTEMPTS = 5


def _slug_base(name: str) -> str:
    lowered = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "org"


def _generate_unique_slug(name: str) -> str:
    """Checked, not guaranteed - see the retry loop in create_organization
    for what actually closes the race between this check and the insert."""
    base = _slug_base(name)
    candidate = base
    suffix = 2
    while db.session.query(Organization).filter_by(slug=candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_organization(creator: User, name: str, **optional_fields) -> Organization:
    """Creates an Organization and makes `creator` its Owner, atomically -
    both rows commit together or neither persists. Retries slug
    generation on a uniqueness race (two concurrent requests computing
    the same slug before either commits), same pattern as FD-009's
    email-uniqueness handling.
    """
    last_error = None

    for attempt in range(_MAX_SLUG_ATTEMPTS):
        slug = _generate_unique_slug(name)
        if attempt > 0:
            # A prior attempt's pre-check already lost a race once;
            # disambiguate further instead of recomputing the same
            # candidate and colliding again immediately.
            slug = f"{slug}-{secrets.token_hex(3)}"

        organization = Organization(name=name, slug=slug, **optional_fields)
        db.session.add(organization)
        try:
            db.session.flush()  # assign organization.id without committing yet
        except IntegrityError:
            db.session.rollback()
            last_error = "slug collision on insert"
            continue

        membership = Membership(organization_id=organization.id, user_id=creator.id, role=MembershipRole.OWNER)
        db.session.add(membership)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            last_error = "slug collision on commit"
            continue

        return organization

    raise RuntimeError(f"Could not generate a unique organization slug after {_MAX_SLUG_ATTEMPTS} attempts: {last_error}")


def list_user_memberships(user: User) -> list[Membership]:
    """Always scoped to `user` - the caller's own memberships, never
    another user's. There is no cross-tenant risk here by construction:
    this never takes an organization_id or another user_id as input."""
    return (
        db.session.query(Membership)
        .filter_by(user_id=user.id)
        .options(joinedload(Membership.organization))
        .order_by(Membership.joined_at.asc())
        .all()
    )
