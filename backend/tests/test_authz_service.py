import uuid

import pytest

from app.authz.permissions import PermissionScope
from app.authz.service import can_assign_role, check_scope_allows, get_active_membership_or_404
from app.errors import APIError
from app.extensions import db
from app.models import Membership, MembershipRole, MembershipStatus, Organization, User


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(Membership).delete()
        db.session.query(Organization).delete()
        db.session.query(User).delete()
        db.session.commit()


def _make_user(app, email):
    with app.app_context():
        user = User(name="Test User", email=email)
        user.set_password("correct horse battery")
        db.session.add(user)
        db.session.commit()
        return user.id


def _make_org(app, name, slug):
    with app.app_context():
        organization = Organization(name=name, slug=slug)
        db.session.add(organization)
        db.session.commit()
        return organization.id


def _make_membership(app, organization_id, user_id, role, status=MembershipStatus.ACTIVE):
    with app.app_context():
        membership = Membership(organization_id=organization_id, user_id=user_id, role=role, status=status)
        db.session.add(membership)
        db.session.commit()
        return membership.id


class TestGetActiveMembershipOr404:
    def test_returns_the_membership_when_active(self, app):
        user_id = _make_user(app, "member@example.com")
        org_id = _make_org(app, "Org", "org")
        _make_membership(app, org_id, user_id, MembershipRole.OWNER)

        with app.app_context():
            user = db.session.get(User, user_id)
            membership = get_active_membership_or_404(user, org_id)
            assert membership.organization_id == org_id
            assert membership.user_id == user_id

    def test_raises_404_when_no_membership_exists(self, app):
        user_id = _make_user(app, "stranger@example.com")
        org_id = _make_org(app, "Org", "org")

        with app.app_context():
            user = db.session.get(User, user_id)
            with pytest.raises(APIError) as exc_info:
                get_active_membership_or_404(user, org_id)
            assert exc_info.value.status_code == 404

    def test_raises_404_for_a_cross_tenant_membership(self, app):
        """The user IS a member of some org, just not this one - still a
        plain 404, never a 403, and never anything that would confirm
        the target org exists to someone probing it."""
        user_id = _make_user(app, "cross-tenant@example.com")
        own_org_id = _make_org(app, "Own Org", "own-org")
        other_org_id = _make_org(app, "Other Org", "other-org")
        _make_membership(app, own_org_id, user_id, MembershipRole.OWNER)

        with app.app_context():
            user = db.session.get(User, user_id)
            with pytest.raises(APIError) as exc_info:
                get_active_membership_or_404(user, other_org_id)
            assert exc_info.value.status_code == 404

    def test_raises_404_when_membership_is_inactive(self, app):
        user_id = _make_user(app, "deactivated@example.com")
        org_id = _make_org(app, "Org", "org")
        _make_membership(app, org_id, user_id, MembershipRole.EMPLOYEE, status=MembershipStatus.INACTIVE)

        with app.app_context():
            user = db.session.get(User, user_id)
            with pytest.raises(APIError) as exc_info:
                get_active_membership_or_404(user, org_id)
            assert exc_info.value.status_code == 404

    def test_raises_404_when_membership_is_suspended(self, app):
        user_id = _make_user(app, "suspended-member@example.com")
        org_id = _make_org(app, "Org", "org")
        _make_membership(app, org_id, user_id, MembershipRole.EMPLOYEE, status=MembershipStatus.SUSPENDED)

        with app.app_context():
            user = db.session.get(User, user_id)
            with pytest.raises(APIError) as exc_info:
                get_active_membership_or_404(user, org_id)
            assert exc_info.value.status_code == 404

    def test_raises_404_for_a_malformed_organization_id_rather_than_a_500(self, app):
        """A bad organization_id can never resolve to a real membership -
        reject it with the same 404 as "no membership", instead of
        letting it reach the DB as an invalid filter value."""
        user_id = _make_user(app, "malformed@example.com")

        with app.app_context():
            user = db.session.get(User, user_id)
            with pytest.raises(APIError) as exc_info:
                get_active_membership_or_404(user, "not-a-uuid")
            assert exc_info.value.status_code == 404


class TestCheckScopeAllows:
    def test_none_never_allows(self):
        caller_id = uuid.uuid4()
        assert check_scope_allows(PermissionScope.NONE, caller_id=caller_id) is False

    def test_full_and_limited_always_allow_at_the_gate_level(self):
        caller_id = uuid.uuid4()
        assert check_scope_allows(PermissionScope.FULL, caller_id=caller_id) is True
        assert check_scope_allows(PermissionScope.LIMITED, caller_id=caller_id) is True

    def test_own_only_allows_the_callers_own_record(self):
        caller_id = uuid.uuid4()
        other_id = uuid.uuid4()
        assert check_scope_allows(PermissionScope.OWN, caller_id=caller_id, owner_id=caller_id) is True
        assert check_scope_allows(PermissionScope.OWN, caller_id=caller_id, owner_id=other_id) is False
        assert check_scope_allows(PermissionScope.OWN, caller_id=caller_id, owner_id=None) is False

    def test_assigned_only_allows_a_record_assigned_to_the_caller(self):
        caller_id = uuid.uuid4()
        other_id = uuid.uuid4()
        assert check_scope_allows(PermissionScope.ASSIGNED, caller_id=caller_id, assignee_id=caller_id) is True
        assert check_scope_allows(PermissionScope.ASSIGNED, caller_id=caller_id, assignee_id=other_id) is False
        assert check_scope_allows(PermissionScope.ASSIGNED, caller_id=caller_id, assignee_id=None) is False


class TestCanAssignRole:
    def test_no_one_can_change_their_own_role_even_the_owner(self, app):
        """Section 13's mandatory scenario, generalized to every role -
        self-escalation (or an owner accidentally self-demoting out of
        their own org) is never allowed through this path."""
        user_id = _make_user(app, "owner@example.com")
        org_id = _make_org(app, "Org", "org")
        membership_id = _make_membership(app, org_id, user_id, MembershipRole.OWNER)

        with app.app_context():
            membership = db.session.get(Membership, membership_id)
            assert can_assign_role(membership, membership, MembershipRole.MANAGER) is False

    def test_owner_can_assign_any_role_to_another_member(self, app):
        owner_id = _make_user(app, "owner2@example.com")
        target_id = _make_user(app, "target@example.com")
        org_id = _make_org(app, "Org", "org")
        owner_membership_id = _make_membership(app, org_id, owner_id, MembershipRole.OWNER)
        target_membership_id = _make_membership(app, org_id, target_id, MembershipRole.EMPLOYEE)

        with app.app_context():
            owner_membership = db.session.get(Membership, owner_membership_id)
            target_membership = db.session.get(Membership, target_membership_id)
            assert can_assign_role(owner_membership, target_membership, MembershipRole.MANAGER) is True

    def test_manager_can_promote_an_employee_to_accountant(self, app):
        manager_id = _make_user(app, "manager@example.com")
        target_id = _make_user(app, "target2@example.com")
        org_id = _make_org(app, "Org", "org")
        manager_membership_id = _make_membership(app, org_id, manager_id, MembershipRole.MANAGER)
        target_membership_id = _make_membership(app, org_id, target_id, MembershipRole.EMPLOYEE)

        with app.app_context():
            manager_membership = db.session.get(Membership, manager_membership_id)
            target_membership = db.session.get(Membership, target_membership_id)
            assert can_assign_role(manager_membership, target_membership, MembershipRole.ACCOUNTANT) is True

    def test_manager_cannot_promote_anyone_to_owner_or_manager(self, app):
        manager_id = _make_user(app, "manager2@example.com")
        target_id = _make_user(app, "target3@example.com")
        org_id = _make_org(app, "Org", "org")
        manager_membership_id = _make_membership(app, org_id, manager_id, MembershipRole.MANAGER)
        target_membership_id = _make_membership(app, org_id, target_id, MembershipRole.EMPLOYEE)

        with app.app_context():
            manager_membership = db.session.get(Membership, manager_membership_id)
            target_membership = db.session.get(Membership, target_membership_id)
            assert can_assign_role(manager_membership, target_membership, MembershipRole.OWNER) is False
            assert can_assign_role(manager_membership, target_membership, MembershipRole.MANAGER) is False

    def test_manager_cannot_change_an_owners_or_another_managers_role(self, app):
        manager_id = _make_user(app, "manager3@example.com")
        owner_id = _make_user(app, "owner3@example.com")
        other_manager_id = _make_user(app, "manager4@example.com")
        org_id = _make_org(app, "Org", "org")
        manager_membership_id = _make_membership(app, org_id, manager_id, MembershipRole.MANAGER)
        owner_membership_id = _make_membership(app, org_id, owner_id, MembershipRole.OWNER)
        other_manager_membership_id = _make_membership(app, org_id, other_manager_id, MembershipRole.MANAGER)

        with app.app_context():
            manager_membership = db.session.get(Membership, manager_membership_id)
            owner_membership = db.session.get(Membership, owner_membership_id)
            other_manager_membership = db.session.get(Membership, other_manager_membership_id)
            assert can_assign_role(manager_membership, owner_membership, MembershipRole.EMPLOYEE) is False
            assert can_assign_role(manager_membership, other_manager_membership, MembershipRole.EMPLOYEE) is False

    def test_manager_cannot_change_a_role_in_a_different_organization(self, app):
        """Regression for the gap tenant-security-reviewer found in
        FD-015's own review: can_assign_role must not trust that both
        memberships belong to the same organization just because
        role-level checks happen to pass."""
        manager_id = _make_user(app, "cross-org-manager@example.com")
        target_id = _make_user(app, "cross-org-target@example.com")
        manager_org_id = _make_org(app, "Manager's Org", "managers-org")
        other_org_id = _make_org(app, "Other Org", "other-org-2")
        manager_membership_id = _make_membership(app, manager_org_id, manager_id, MembershipRole.MANAGER)
        target_membership_id = _make_membership(app, other_org_id, target_id, MembershipRole.EMPLOYEE)

        with app.app_context():
            manager_membership = db.session.get(Membership, manager_membership_id)
            target_membership = db.session.get(Membership, target_membership_id)
            # Role-level logic alone would allow this (Employee -> Accountant
            # is within a Manager's permitted set) - only the organization
            # mismatch must block it.
            assert can_assign_role(manager_membership, target_membership, MembershipRole.ACCOUNTANT) is False

    def test_employee_cannot_change_anyones_role(self, app):
        employee_id = _make_user(app, "employee@example.com")
        target_id = _make_user(app, "target4@example.com")
        org_id = _make_org(app, "Org", "org")
        employee_membership_id = _make_membership(app, org_id, employee_id, MembershipRole.EMPLOYEE)
        target_membership_id = _make_membership(app, org_id, target_id, MembershipRole.EMPLOYEE)

        with app.app_context():
            employee_membership = db.session.get(Membership, employee_membership_id)
            target_membership = db.session.get(Membership, target_membership_id)
            assert can_assign_role(employee_membership, target_membership, MembershipRole.ACCOUNTANT) is False
