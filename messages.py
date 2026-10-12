"""Fixed sentences. English first. The Japanese credit is the API terms, article 7, uncut."""
from __future__ import annotations

CREDIT = (
    "「このサービスは、国土交通省の不動産情報ライブラリのAPI機能を使用していますが、"
    "提供情報の最新性、正確性、完全性等が保証されたものではありません」"
)
ATTRIBUTION = "出典：国土交通省\u3000不動産情報ライブラリ"
TOP_URL = "https://www.reinfolib.mlit.go.jp/"
PROCESSING = "「不動産取引価格情報」（国土交通省）をもとに件数と抜粋を作成"
PRICE_CATEGORY = "不動産取引価格情報"

ERRORS = {
    "invalid_argument": "The arguments were refused before any request was sent.",
    "bad_city": "This designated-city code was refused before any request was sent. Use a ward code.",
    "config": "The plugin is not configured, so nothing was requested.",
    "auth": "The request was refused. This is not an empty result.",
    "rate_limited": "The server returned HTTP 429. The request was not retried.",
    "not_found": (
        "HTTP 404 means no data for this city, year, and quarter. "
        "It is not zero rows and it is not unchanged prices. "
        "A city code of the right shape with no published rows is the same 404, "
        "and those two cases are not separated."
    ),
    "redirect": "The redirect was not followed.",
    "timeout": "No bytes arrived for 30 seconds. It was not retried.",
    "invalid_response": "The response was not a usable result.",
    "upstream": "The request failed. It was not retried.",
    "internal": "The response was dropped.",
}

# missing_key only. bad_origin and key_in_url stay on ERRORS["config"].
MISSING_KEY = "REINFOLIB_API_KEY is unset, so nothing was requested."
