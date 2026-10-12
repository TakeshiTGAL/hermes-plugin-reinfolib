"""One GET. Redirects are not followed. The gap is in memory, per process, and is not saved."""
from __future__ import annotations

import gzip
import io
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

if __package__:
    from .schema import BODY_CAP, MIN_GAP_SECONDS, TIMEOUT_SECONDS
else:
    from schema import BODY_CAP, MIN_GAP_SECONDS, TIMEOUT_SECONDS

PATH = "/ex-api/external/XIT001"
HEADER = "Ocp-Apim-Subscription-Key"
Transport = Callable[[str, dict[str, str], float, int], tuple[int, dict[str, str], bytes]]


class CallError(Exception):
    def __init__(self, error_type: str, detail: str, status_code: int | None = None) -> None:
        super().__init__(error_type)
        self.error_type = error_type
        self.detail = detail
        self.status_code = status_code


@dataclass
class Origin:
    value: str
    scheme: str
    host: str


def parse_origin(raw: str) -> Origin:
    text = raw if raw else "https://www.reinfolib.mlit.go.jp"
    if text != text.strip() or any(ch.isspace() for ch in text) or "\\" in text:
        raise CallError("config", "bad_origin")
    parts = urllib.parse.urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.hostname or not parts.netloc:
        raise CallError("config", "bad_origin")
    if parts.username or parts.password or parts.path not in {"",} or parts.query or parts.fragment:
        raise CallError("config", "bad_origin")
    host = parts.hostname
    if parts.scheme == "http" and host not in {"127.0.0.1", "localhost"}:
        raise CallError("config", "bad_origin")
    return Origin(f"{parts.scheme}://{parts.netloc}", parts.scheme, host)


class Gap:
    """At least MIN_GAP_SECONDS between outbound GETs in this process. Not shared across processes."""

    def __init__(self, now: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._next = 0.0
        self._now = now or time.monotonic
        self._sleep = sleep or time.sleep

    def run(self, call: Callable[[], Any]) -> Any:
        """Run one outbound call. The next call waits until 1 second after this one returns."""
        with self._lock:
            delay = self._next - self._now()
            if delay > 0:
                self._sleep(delay)
            try:
                return call()
            finally:
                self._next = self._now() + MIN_GAP_SECONDS


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def default_transport(url: str, headers: dict[str, str], timeout: float, cap: int) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    # ProxyHandler({}) replaces urllib's default, so an environment proxy does not
    # receive the Ocp-Apim-Subscription-Key header. _NoRedirect replaces the redirect handler.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = _read_capped(response, cap)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, payload
    except urllib.error.HTTPError as error:
        payload = _read_capped(error, cap)
        return error.code, {k.lower(): v for k, v in error.headers.items()}, payload
    except TimeoutError as error:
        raise CallError("timeout", "timeout") from error
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError):
            raise CallError("timeout", "timeout") from error
        raise CallError("upstream", "network") from error


def _read_capped(response: Any, cap: int) -> bytes:
    try:
        return response.read(cap + 1)
    except Exception as error:
        raise CallError("invalid_response", "short_body") from error


def _gunzip(payload: bytes, cap: int) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as handle:
            return handle.read(cap + 1)
    except Exception as error:
        raise CallError("invalid_response", "bad_gzip") from error


DEFAULT_GAP = Gap()


class Client:
    def __init__(self, origin: Origin, key: str, transport: Transport | None = None, gap: Gap | None = None) -> None:
        if not isinstance(key, str) or key == "" or key != key.strip() or any(ch.isspace() for ch in key):
            raise CallError("config", "missing_key")
        self.origin = origin
        self.key = key
        self.transport = transport or default_transport
        self.gap = DEFAULT_GAP if gap is None else gap

    def get_quarter(self, year: int, quarter: int, city: str) -> tuple[int, dict[str, str], bytes]:
        query = urllib.parse.urlencode(
            [
                ("year", str(year)),
                ("quarter", str(quarter)),
                ("city", city),
                ("priceClassification", "01"),
                ("language", "ja"),
            ]
        )
        url = f"{self.origin.value}{PATH}?{query}"
        if self.key in url:
            raise CallError("config", "key_in_url")
        headers = {"Accept": "application/json", HEADER: self.key}

        def _send() -> tuple[int, dict[str, str], bytes]:
            try:
                return self.transport(url, headers, TIMEOUT_SECONDS, BODY_CAP)
            except CallError:
                raise
            except TimeoutError as error:
                raise CallError("timeout", "timeout") from error
            except Exception as error:
                raise CallError("upstream", "network") from error

        status, response_headers, payload = self.gap.run(_send)
        return self._finish(status, response_headers, payload)

    def _finish(self, status: int, headers: dict[str, str], payload: bytes) -> tuple[int, dict[str, str], bytes]:
        lowered = {str(key).lower(): str(value) for key, value in headers.items()}
        if 300 <= status < 400:
            raise CallError("redirect", "redirect", status)
        declared = lowered.get("content-length")
        declared_n = int(declared.strip()) if declared and declared.strip().isdigit() else None
        if declared_n is not None and declared_n > BODY_CAP:
            raise CallError("invalid_response", "too_big", status)
        if len(payload) > BODY_CAP:
            raise CallError("invalid_response", "too_big", status)
        if declared_n is not None and len(payload) < declared_n:
            raise CallError("invalid_response", "short_body", status)
        encoding = lowered.get("content-encoding", "").strip().lower()
        if encoding == "gzip":
            payload = _gunzip(payload, BODY_CAP)
            if len(payload) > BODY_CAP:
                raise CallError("invalid_response", "too_big", status)
        elif encoding not in {"", "identity"}:
            raise CallError("invalid_response", "bad_encoding", status)
        return status, lowered, payload
