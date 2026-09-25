"""Strict dashboard user-administration request models."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.dashboard_management import _label
from app.users.service import UserRole, normalize_email


class UserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("role", mode="before", check_fields=False)
    @classmethod
    def role_value(cls, value: object) -> UserRole | None:
        if value is None or isinstance(value, UserRole):
            return value
        if not isinstance(value, str):
            raise ValueError("invalid role")
        try:
            return UserRole(value)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid role") from error


class UserCreateRequest(UserRequest):
    email: str
    display_name: str | None = Field(default=None, max_length=128)
    role: UserRole

    @field_validator("email", mode="before")
    @classmethod
    def email_value(cls, value: object) -> str:
        return normalize_email(value)

    @field_validator("display_name", mode="before")
    @classmethod
    def name_value(cls, value: object) -> str | None:
        return None if value is None else _label(value)


class UserUpdateRequest(UserRequest):
    display_name: str | None = Field(default=None, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def name_value(cls, value: object) -> str | None:
        return None if value is None else _label(value)
