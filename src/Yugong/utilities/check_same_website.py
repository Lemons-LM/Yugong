"""Domain matching for ``apply_websites`` in template rules."""

from __future__ import annotations

from urllib.parse import urlparse

from src.Yugong.core.settings import settings


def normalize_domain(domain: str) -> str:
    """Lower-case a host, dropping a ``www.`` prefix and any port."""
    if not domain:
        return ""
    domain = domain.lower().split(":")[0]
    if domain.startswith("www."):
        return domain[4:]
    return domain


def extract_domain(address: str) -> str:
    """Return the host part of a URL or bare domain."""
    if not address:
        return ""
    netloc = urlparse(address).netloc
    if not netloc and not address.startswith(("http://", "https://")):
        netloc = urlparse(f"https://{address}").netloc
    return netloc


def check_same_website(url: str, *, api_endpoint: str | None = None) -> bool:
    """Return ``True`` if *url* points at the same host as the configured wiki."""
    if api_endpoint is None:
        api_endpoint = str(getattr(settings, "api_endpoint", ""))

    try:
        url_domain = normalize_domain(extract_domain(url))
        if not url_domain:
            return False

        api_domain = normalize_domain(extract_domain(api_endpoint))
        if not api_domain:
            return False

        return url_domain == api_domain
    except Exception:  # noqa: BLE001 - a malformed rule URL must not crash the run
        return False
