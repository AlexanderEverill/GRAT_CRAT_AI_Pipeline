# src/retrieval/allowlist.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set, Optional
from urllib.parse import urlparse


def normalize_host(host: str) -> str:
    """
    Normalize a hostname for allowlist comparisons.
    - lowercase
    - strip whitespace
    - strip leading 'www.'
    """
    host = (host or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def host_from_url(url: str) -> Optional[str]:
    """
    Extract hostname from URL.
    Returns None if parsing fails or hostname is invalid.
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    # If it looks like a full URL
    if "://" in url:
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                return None
            return normalize_host(host)
        except Exception:
            return None

    # If it looks like a bare domain (e.g. law.cornell.edu)
    if "." in url and " " not in url:
        return normalize_host(url)

    return None


@dataclass(frozen=True)
class Allowlist:
    domains: Set[str]

    @classmethod
    def from_domains(cls, domains: Iterable[str]) -> "Allowlist":
        normalized = {normalize_host(d) for d in domains if normalize_host(d)}
        return cls(domains=normalized)

    def is_allowed_host(self, host: str) -> bool:
        host = normalize_host(host)
        if not host:
            return False

        # Exact host match OR subdomain match
        # e.g. allow "irs.gov" should allow "www.irs.gov" and "apps.irs.gov"
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def is_allowed_url(self, url: str) -> bool:
        host = host_from_url(url)
        if not host:
            return False
        return self.is_allowed_host(host)
