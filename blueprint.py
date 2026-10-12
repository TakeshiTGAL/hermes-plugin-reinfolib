"""Weekly read of one city.

Registered only when ctx.register_automation_blueprint is callable. Otherwise
registration is skipped and the bundled skill has the same steps. A missing
method is not an error. This function does not create a cron job.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

KEY = "weekly-city-check"
TITLE = "Weekly city transaction check"
CADENCE = "once a week"
DEFAULT_DAY_LABEL = "Monday"
DEFAULT_TIME = "09:00"
DESCRIPTION = (
    f"{CADENCE}, read one city's MLIT transaction prices for the latest "
    "started quarter and the quarter before it. The default day is "
    f"{DEFAULT_DAY_LABEL} and the default time is {DEFAULT_TIME}. "
    "HTTP 404 means no rows for that request. It does not mean prices are "
    "unchanged, and this check does not remember a previous count. "
    "A week whose reads are all HTTP 404 may be answered as [SILENT] and not delivered. "
    "Publication lags the quarter, so many weeks have no new rows. "
    "A municipality name is not a city code. "
    "A week with data is one short message. "
    "This plugin does not create a cron job."
)
SCHEDULE_TEMPLATE = "{minute} {hour} * * {dow}"
PROMPT_TEMPLATE = """\
Read MLIT transaction prices for city {city}. Call only reinfolib_quarter. \
Use the computer's local date. A quarter starts in January, April, July, or October. \
Call the tool once for the latest started quarter and once for the quarter before it. \
Pass city, year, and quarter. city is a 5-digit code, not a municipality name. Example: 13104 is Shinjuku-ku. \
A designated city needs a ward code, not the city code. Example: 14101, not 14100. \
price_classification is 01 and language is ja. \
If a call is invalid_argument with detail bad_city, explain that code and where to find it (MLIT XIT002, or the national local-government code). \
Do not use [SILENT] for that failure. This plugin does not look names up. \
Publication lags the quarter, so the latest started quarter is often HTTP 404 for many weeks.

Hermes delivers the final answer. When there is nothing to report, answer with exactly \
[SILENT] and nothing else, which suppresses delivery. This plugin does not remember a previous count, \
so it cannot tell whether rows are new or prices are unchanged.

If every call is error_type not_found, there is no data for those quarters. \
That is not zero rows and not unchanged prices. A city code of the right shape with no published rows is the same 404, and those two cases are not separated. \
Answer exactly [SILENT] and nothing else.

If any call has ok true, send one short message and do not use [SILENT]. \
For each call report period, count, and truncated. Include attribution and processing unchanged. \
count is the full length. records is at most 20 rows and only these columns: \
Type, Region, MunicipalityCode, Prefecture, Municipality, DistrictName, TradePrice, PricePerUnit, Area, UnitPrice, Period, PriceCategory. \
Do not say that rows are new, and do not say that prices are unchanged.

If the JSON has ok false and error_type is not not_found:
- error_type timeout, upstream, rate_limited, auth, redirect, or invalid_response: the check failed. \
Name error_type and status_code. Do not use [SILENT]. Do not treat the failure as no change.
- error_type invalid_argument or config: the call was refused before a request. Name detail. Do not use [SILENT].
- error_type internal: the response was dropped. Do not guess the rows. Do not use [SILENT].
If the tool is missing: say jp-reinfolib is not loaded. Do not guess.
"""
SLOTS = (
    {
        "name": "city",
        "type": "text",
        "label": "Which city code?",
        "help": "A 5-digit code, not the municipality name. Example: 13104 is Shinjuku-ku. The first two digits are 01 through 47. A designated city needs a ward code, not the city code. Publication lags the quarter, so many weeks have no new rows.",
    },
    {
        "name": "day",
        "type": "enum",
        "label": "Which day?",
        "default": "monday",
        "options": ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"),
        "strict": True,
        "help": f"One weekday. The default label is {DEFAULT_DAY_LABEL}. Hermes's timezone, or the computer's clock if none is set.",
    },
    {
        "name": "time",
        "type": "time",
        "label": "What time?",
        "default": DEFAULT_TIME,
        "help": f"24-hour time in Hermes's timezone, or the computer's clock if none is set. Example: {DEFAULT_TIME}.",
    },
)
DELIVER_DEFAULT = "origin"
SKILL_NAME = "weekly-city-check"


def register_blueprint(ctx) -> bool:
    """True only when Hermes accepted the blueprint. Never raises."""
    register = getattr(ctx, "register_automation_blueprint", None)
    if not callable(register):
        return False
    try:
        accepted = register(
            KEY,
            title=TITLE,
            description=DESCRIPTION,
            category="weekly",
            schedule_template=SCHEDULE_TEMPLATE,
            prompt_template=PROMPT_TEMPLATE,
            slots=list(SLOTS),
            deliver_default=DELIVER_DEFAULT,
            skills=[],
            tags=["japan", "mlit"],
        )
    except Exception:
        logger.warning("jp-reinfolib: automation blueprint was not registered")
        return False
    return accepted is not None
