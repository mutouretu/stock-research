"""Small HTTP helper shared by public data adapters."""

from __future__ import annotations

import ssl
from urllib.request import Request, urlopen

import certifi


DEFAULT_USER_AGENT = "stock-research/0.1 data-research"


def fetch_bytes(url: str, *, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 60) -> bytes:
    request = Request(url, headers={"User-Agent": user_agent})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=timeout, context=context) as response:
        return response.read()
