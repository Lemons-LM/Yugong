"""Normalisation of the wiki URL configured in ``settings.toml``.

``api_endpoint`` is documented as "the directory holding ``api.php``, with a
trailing slash".  The raw-API helpers, however, need the ``api.php`` URL, and
the manual-review mode needs the directory again to open ``index.php``.  Keeping
both spellings in one place means a configured value works no matter whether the
operator wrote ``https://wiki.example/`` or ``https://wiki.example/api.php``.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Recognised URL schemes.
SUPPORTED_SCHEMES: tuple[str, ...] = ("http", "https")


def _clean(endpoint: str) -> str:
    return str(endpoint or "").strip()


def split_endpoint(endpoint: str) -> tuple[str, str, str]:
    """Return ``(scheme, netloc, path)`` for *endpoint* (empty parts if unset)."""
    parsed = urlparse(_clean(endpoint))
    return parsed.scheme.lower(), parsed.netloc, parsed.path


def is_supported_url(endpoint: str) -> bool:
    """Return ``True`` when *endpoint* is an absolute http(s) URL with a host.

    Embedded credentials (``https://user:pass@host/``) are rejected: the
    endpoint is printed by ``settings.describe()`` and written to the logs, so a
    password there would leak.  OAuth belongs in the environment.
    """
    scheme, netloc, _ = split_endpoint(endpoint)
    parsed = urlparse(_clean(endpoint))
    return (
        scheme in SUPPORTED_SCHEMES
        and bool(netloc)
        and parsed.username is None
        and parsed.password is None
        and " " not in _clean(endpoint)
    )


def base_url(endpoint: str) -> str:
    """Return the wiki's directory URL, always ending in ``/``.

    ``https://wiki.example/api.php`` and ``https://wiki.example`` both become
    ``https://wiki.example/``.
    """
    scheme, netloc, path = split_endpoint(endpoint)
    if not scheme or not netloc:
        return ""

    if path.endswith("api.php"):
        path = path[: -len("api.php")]
    path = path.rstrip("/")
    return f"{scheme}://{netloc}{path}/"


def api_url(endpoint: str) -> str:
    """Return the ``api.php`` URL for *endpoint*."""
    base = base_url(endpoint)
    if not base:
        return ""
    return f"{base}api.php"


def script_path(endpoint: str) -> str:
    """Return the install path (the ``scriptpath``) without a trailing slash.

    ``https://wiki.example/w/api.php`` -> ``/w``; a wiki at the domain root
    returns ``""``.
    """
    base = base_url(endpoint)
    if not base:
        return ""
    path = urlparse(base).path.rstrip("/")
    return path


def host_of(endpoint: str) -> str:
    """Return the host (with port, if any), or ``""``."""
    return split_endpoint(endpoint)[1]


def scheme_of(endpoint: str, *, default: str = "https") -> str:
    """Return the endpoint's scheme, falling back to *default*."""
    scheme = split_endpoint(endpoint)[0]
    return scheme if scheme in SUPPORTED_SCHEMES else default
