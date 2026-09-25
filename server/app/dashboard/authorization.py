"""Reusable server-side dashboard role dependencies."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException

from app.dashboard.service import DashboardUser
from app.users.service import UserRole


def requires(
    user_dependency: Callable[..., Awaitable[DashboardUser]], *roles: UserRole
) -> Callable[..., Awaitable[DashboardUser]]:
    """Return a dependency that rejects authenticated users without a listed role."""

    async def dependency(
        user: Annotated[DashboardUser, Depends(user_dependency)],
    ) -> DashboardUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Dashboard permission is denied.",
                headers={"Cache-Control": "no-store"},
            )
        return user

    return dependency
