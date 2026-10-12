"""Generated from schema.TYPES, COLUMNS, ARGUMENTS, and PAIRS. No sockets."""
from __future__ import annotations

import json

from schema import (
    COLUMNS,
    EXAMPLE_CTX,
    EXAMPLE_TODAY,
    PAIRS,
    TYPES,
    ARGUMENTS,
    project_body,
    validate_arguments,
)

PARSED = {
    "city": "13102",
    "year": 2015,
    "quarter": 2,
    "price_classification": "01",
    "language": "ja",
}


def _good_row() -> dict:
    return {column["name"]: column["sample"] for column in COLUMNS}


def test_every_type_has_examples_and_is_used():
    used = {row["type"] for row in ARGUMENTS} | {column["type"] for column in COLUMNS}
    assert used <= set(TYPES)
    for name, spec in TYPES.items():
        assert spec["accept"], name
        assert spec["reject"], name
        assert "check" in spec, name


def test_type_examples():
    for name, spec in TYPES.items():
        for value in spec["accept"]:
            assert spec["check"](value, EXAMPLE_CTX), (name, value)
        for value in spec["reject"]:
            assert not spec["check"](value, EXAMPLE_CTX), (name, value)


def test_pairs():
    for row in PAIRS:
        args = {"city": "13102", "year": row["year"], "quarter": row["quarter"]}
        parsed, detail = validate_arguments(args, row["today"])
        if row["ok"]:
            assert parsed is not None and detail is None, row
        else:
            assert parsed is None and detail in {"bad_quarter", "future_quarter"}, row


def test_sample_row_projects():
    body = json.dumps({"status": "OK", "data": [_good_row()]}).encode()
    records, detail = project_body(body, PARSED, EXAMPLE_TODAY)
    assert detail is None and records == [_good_row()]


def test_each_column_reject_keeps_the_row_unless_the_request_does_not_match():
    hard = {"Period", "PriceCategory"}
    for column in COLUMNS:
        for value in TYPES[column["type"]]["reject"]:
            row = _good_row()
            row[column["name"]] = value
            body = json.dumps({"status": "OK", "data": [row]}, ensure_ascii=False).encode()
            records, detail = project_body(body, PARSED, EXAMPLE_TODAY)
            if column["name"] in hard:
                assert records is None and detail == "mismatched_record", (column["name"], value)
            else:
                assert detail is None and records is not None, (column["name"], value)
                assert isinstance(records[0][column["name"]], dict), (column["name"], value)


def test_missing_or_null_column_fails_and_unknown_column_is_dropped():
    for column in COLUMNS:
        row = _good_row()
        del row[column["name"]]
        body = json.dumps({"status": "OK", "data": [row]}).encode()
        records, detail = project_body(body, PARSED, EXAMPLE_TODAY)
        assert records is None and detail == "bad_record", column["name"]
    row = _good_row()
    row["Remarks"] = "keep-me-out"
    row["DistrictCode"] = "131020170"
    body = json.dumps({"status": "OK", "data": [row]}).encode()
    records, detail = project_body(body, PARSED, EXAMPLE_TODAY)
    assert detail is None
    assert "Remarks" not in records[0] and "DistrictCode" not in records[0]


def test_unknown_argument_is_refused():
    parsed, detail = validate_arguments(
        {"city": "13102", "year": 2015, "quarter": 2, "area": "01"},
        EXAMPLE_TODAY,
    )
    assert parsed is None and detail == "unknown_argument"
