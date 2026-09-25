"""Application user persistence; never used as a replacement for Google OIDC."""

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select

from app.db import Database, database_utc
from app.models import ApplicationUser, AuditEvent


class UserRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    USER = "USER"


class UserError(RuntimeError):
    """Safe application-user lifecycle failure."""


class OwnerAlreadyConfigured(UserError):
    """A different sole Owner already exists."""


class UserConflict(UserError):
    """A requested durable-user change violates a safety rule."""


class UserPermissionDenied(UserError):
    """The current role cannot make the requested application-user change."""


@dataclass(frozen=True)
class OwnerBootstrapResult:
    user: ApplicationUser
    already_configured: bool


def normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid email")
    normalized = value.strip().lower()
    if not re.fullmatch(r"[^\s@\r\n]{1,64}@[^\s@\r\n]{1,255}", normalized):
        raise ValueError("invalid email")
    return normalized


def authorize_user_change(
    actor_role: UserRole,
    *,
    target_role: UserRole | None = None,
    requested_role: UserRole | None = None,
) -> None:
    """Enforce the sole-Owner user-administration matrix at the service boundary."""

    if target_role is UserRole.OWNER or requested_role is UserRole.OWNER:
        raise UserPermissionDenied("Owner administration is restricted to local bootstrap.")
    if actor_role is UserRole.OWNER:
        return
    if (
        actor_role is UserRole.ADMIN
        and target_role in {None, UserRole.USER}
        and requested_role
        in {
            None,
            UserRole.USER,
        }
    ):
        return
    raise UserPermissionDenied("Role cannot administer the requested account.")


class UserService:
    def __init__(
        self, database: Database, *, actor: str, actor_role: UserRole | None = None
    ) -> None:
        self.database = database
        self.actor = actor
        self.actor_role = actor_role

    def _authorize(
        self, *, target_role: UserRole | None = None, requested_role: UserRole | None = None
    ) -> None:
        if self.actor_role is None:
            raise UserPermissionDenied("Dashboard role is required for user administration.")
        authorize_user_change(
            self.actor_role, target_role=target_role, requested_role=requested_role
        )

    def bootstrap_owner(self, email: str) -> OwnerBootstrapResult:
        normalized = normalize_email(email)
        with self.database.transaction() as session:
            now = database_utc(session)
            owner = session.scalar(
                select(ApplicationUser)
                .where(ApplicationUser.role == UserRole.OWNER.value)
                .with_for_update()
            )
            if owner is not None:
                if owner.email == normalized:
                    return OwnerBootstrapResult(owner, already_configured=True)
                raise OwnerAlreadyConfigured("Owner is already configured.")
            user = ApplicationUser(
                email=normalized,
                display_name=None,
                google_sub=None,
                role=UserRole.OWNER.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.add(
                AuditEvent(
                    actor=self.actor,
                    action="user.owner_bootstrapped",
                    project_id=None,
                    device_id=None,
                    occurred_at=now,
                    details={
                        "affected_email": normalized,
                        "previous_role": None,
                        "new_role": UserRole.OWNER.value,
                        "previous_active": None,
                        "new_active": True,
                    },
                )
            )
            return OwnerBootstrapResult(user, already_configured=False)

    def list_users(self) -> list[ApplicationUser]:
        with self.database.transaction() as session:
            return list(session.scalars(select(ApplicationUser).order_by(ApplicationUser.email)))

    def create_user(
        self, *, email: str, display_name: str | None, role: UserRole
    ) -> ApplicationUser:
        self._authorize(requested_role=role)
        with self.database.transaction() as session:
            now = database_utc(session)
            user = ApplicationUser(
                email=normalize_email(email),
                display_name=display_name,
                google_sub=None,
                role=role.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.add(
                AuditEvent(
                    actor=self.actor,
                    action="user.created",
                    project_id=None,
                    device_id=None,
                    occurred_at=now,
                    details={
                        "affected_email": user.email,
                        "previous_role": None,
                        "new_role": role.value,
                        "previous_active": None,
                        "new_active": True,
                    },
                )
            )
            return user

    def update_user(
        self,
        user_id: int,
        *,
        display_name: str | None,
        role: UserRole | None,
        is_active: bool | None,
    ) -> ApplicationUser:
        with self.database.transaction() as session:
            user = session.get(ApplicationUser, user_id, with_for_update=True)
            if user is None:
                raise UserConflict("User not found.")
            try:
                target_role = UserRole(user.role)
            except ValueError as error:
                raise UserConflict("Stored role is invalid.") from error
            self._authorize(target_role=target_role, requested_role=role)
            now = database_utc(session)
            before_role, before_active = user.role, user.is_active
            if display_name is not None:
                user.display_name = display_name
            if role is not None:
                user.role = role.value
            if is_active is not None:
                user.is_active = is_active
            user.updated_at = now
            session.add(
                AuditEvent(
                    actor=self.actor,
                    action="user.updated",
                    project_id=None,
                    device_id=None,
                    occurred_at=now,
                    details={
                        "affected_email": user.email,
                        "previous_role": before_role,
                        "new_role": user.role,
                        "previous_active": before_active,
                        "new_active": user.is_active,
                    },
                )
            )
            return user
