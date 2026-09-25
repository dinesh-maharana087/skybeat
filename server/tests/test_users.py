from types import SimpleNamespace

import pytest


def test_normalize_user_email_is_case_and_whitespace_stable():
    from app.users.service import normalize_email

    assert normalize_email("  Owner@Example.TEST ") == "owner@example.test"
    with pytest.raises(ValueError):
        normalize_email("not-an-email")


def test_owner_bootstrap_is_idempotent_and_refuses_a_different_owner(monkeypatch):
    from app.users.service import OwnerAlreadyConfigured, UserRole, UserService

    owner = None

    class Session:
        def scalar(self, statement):
            return owner

        def add(self, value):
            nonlocal owner
            if value.__class__.__name__ == "ApplicationUser":
                owner = value

    class Transaction:
        def __enter__(self):
            return Session()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.users.service.database_utc", lambda session: "now")
    service = UserService(
        SimpleNamespace(transaction=lambda: Transaction()), actor="local-operator"
    )

    first = service.bootstrap_owner("  Owner@Example.TEST ")
    again = service.bootstrap_owner("owner@example.test")

    assert first.user.email == "owner@example.test"
    assert first.user.role == UserRole.OWNER.value
    assert not first.already_configured
    assert again.user is owner
    assert again.already_configured
    with pytest.raises(OwnerAlreadyConfigured):
        service.bootstrap_owner("other@example.test")


@pytest.mark.parametrize(
    ("actor_role", "target_role", "requested_role", "allowed"),
    [
        ("OWNER", "ADMIN", "USER", True),
        ("OWNER", "USER", "ADMIN", True),
        ("OWNER", "OWNER", "USER", False),
        ("ADMIN", "USER", "USER", True),
        ("ADMIN", "USER", "ADMIN", False),
        ("ADMIN", "ADMIN", "USER", False),
        ("ADMIN", "OWNER", "USER", False),
        ("USER", "USER", "USER", False),
    ],
)
def test_user_administration_policy_enforces_actor_target_and_role_matrix(
    actor_role, target_role, requested_role, allowed
):
    from app.users.service import UserPermissionDenied, UserRole, authorize_user_change

    if allowed:
        authorize_user_change(
            UserRole(actor_role),
            target_role=UserRole(target_role),
            requested_role=UserRole(requested_role),
        )
    else:
        with pytest.raises(UserPermissionDenied):
            authorize_user_change(
                UserRole(actor_role),
                target_role=UserRole(target_role),
                requested_role=UserRole(requested_role),
            )


@pytest.mark.parametrize(
    ("actor_role", "new_role", "allowed"),
    [
        ("OWNER", "ADMIN", True),
        ("OWNER", "USER", True),
        ("OWNER", "OWNER", False),
        ("ADMIN", "USER", True),
        ("ADMIN", "ADMIN", False),
        ("USER", "USER", False),
    ],
)
def test_user_creation_policy_enforces_role_matrix(actor_role, new_role, allowed):
    from app.users.service import UserPermissionDenied, UserRole, authorize_user_change

    if allowed:
        authorize_user_change(UserRole(actor_role), requested_role=UserRole(new_role))
    else:
        with pytest.raises(UserPermissionDenied):
            authorize_user_change(UserRole(actor_role), requested_role=UserRole(new_role))
