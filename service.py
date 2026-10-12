"""Read one XIT001 quarter. No files, no cron, no saved city."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

if __package__:
    from .client import CallError, Client, Gap, Transport, parse_origin
    from .schema import fail, missing_field, project_body, seal, success, validate_arguments
else:
    from client import CallError, Client, Gap, Transport, parse_origin
    from schema import fail, missing_field, project_body, seal, success, validate_arguments

TOOL_NAME = "reinfolib_quarter"
TOOLSET = "jp_reinfolib"


def _secret(name: str) -> str:
    """Read one profile value at this call. None is unset. UnscopedSecretError is not caught."""
    from agent.secret_scope import get_secret

    value = get_secret(name)
    return value if isinstance(value, str) else ""


def quarter(
    args: Any,
    *,
    today: date | None = None,
    transport: Transport | None = None,
    gap: Gap | None = None,
    key: str | None = None,
    base_url: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    clock = today or date.today()
    parsed, detail = validate_arguments(args, clock)
    if parsed is None:
        if detail == "designated_city":
            return fail("bad_city")
        return fail("invalid_argument", detail=detail, field=missing_field(args, detail))
    try:
        origin = parse_origin(_secret("REINFOLIB_BASE_URL") if base_url is None else base_url)
    except CallError as error:
        return fail(error.error_type, detail=error.detail, status_code=error.status_code)
    api_key = _secret("REINFOLIB_API_KEY") if key is None else key
    try:
        client = Client(origin, api_key, transport=transport, gap=gap)
        status, _headers, payload = client.get_quarter(parsed["year"], parsed["quarter"], parsed["city"])
    except CallError as error:
        return seal(fail(error.error_type, detail=error.detail, status_code=error.status_code), api_key)
    if status == 404:
        return seal(fail("not_found", status_code=404), api_key)
    if status in {401, 403}:
        return seal(fail("auth", status_code=status), api_key)
    if status == 429:
        return seal(fail("rate_limited", status_code=429), api_key)
    if status != 200:
        return seal(fail("upstream", status_code=status), api_key)
    records, body_detail = project_body(payload, parsed, clock)
    if records is None:
        return seal(fail("invalid_response", detail=body_detail, status_code=200), api_key)
    when = fetched_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return seal(success(parsed, records, fetched_at=when), api_key)
