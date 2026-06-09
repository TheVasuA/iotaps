"""Unit tests for telemetry query helpers (Task 5.7, Req 6.6).

Covers the pure pieces of :mod:`app.services.telemetry_service` that do not need
a DB: the resolution -> source allowlist and the JSON column normalisation.
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.services import telemetry_service as ts


def test_resolve_source_covers_all_resolutions():
    assert ts.resolve_source("raw").relation == "telemetry"
    assert ts.resolve_source("raw").time_column == "ts"
    assert ts.resolve_source("5m").relation == "telemetry_5m"
    assert ts.resolve_source("1h").relation == "telemetry_1h"
    assert ts.resolve_source("1d").relation == "telemetry_1d"
    # Rollups all expose the time-bucket column.
    for res in ("5m", "1h", "1d"):
        assert ts.resolve_source(res).time_column == "bucket"


def test_resolve_source_rejects_unknown_resolution():
    with pytest.raises(ValidationError) as excinfo:
        ts.resolve_source("hourly")
    assert excinfo.value.error_code == "invalid_resolution"


def test_resolve_source_rejects_injection_attempt():
    with pytest.raises(ValidationError):
        ts.resolve_source("telemetry; DROP TABLE telemetry")


def test_as_dict_passthrough_dict():
    assert ts._as_dict({"temp": 1}) == {"temp": 1}


def test_as_dict_decodes_json_string():
    assert ts._as_dict('{"temp": 2}') == {"temp": 2}


def test_as_dict_handles_invalid_input():
    assert ts._as_dict("not json") == {}
    assert ts._as_dict(None) == {}
    assert ts._as_dict(42) == {}
