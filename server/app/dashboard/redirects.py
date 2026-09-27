"""Validated local browser return paths for the OIDC flow."""

from urllib.parse import urlsplit

LOGIN_ERROR_MESSAGES = {
    "unavailable": "Google sign-in is temporarily unavailable. Please try again later.",
    "verification_failed": "Google sign-in could not be verified. Please try again.",
    "access_denied": "Your Google account is not authorized for SkyBeat.",
}


def login_error_path(code: str) -> str:
    return f"/login?error={code if code in LOGIN_ERROR_MESSAGES else 'verification_failed'}"


def login_error_message(code: str | None) -> str | None:
    if code is None:
        return None
    return LOGIN_ERROR_MESSAGES.get(code)


def safe_return_path(value: str | None) -> str | None:
    """Return a local absolute path, rejecting every origin-bearing URL."""

    if (
        not value
        or len(value) > 2048
        or "\\" in value
        or any(character.isspace() for character in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return None
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")
