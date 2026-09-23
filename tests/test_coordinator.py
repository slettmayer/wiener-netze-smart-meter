"""Fetching, aggregation and statistics import."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.wiener_netze_smart_meter.api_client import ApiError, AuthenticationError
from custom_components.wiener_netze_smart_meter.const import DOMAIN, ROLES, SERVICE_FETCH_DATA
from custom_components.wiener_netze_smart_meter.coordinator import _aggregate_to_hourly, _parse_meter_reading

from .conftest import COOKIE_DATA, make_entry

TOTAL_STATISTIC_ID = f"{DOMAIN}:total_12345678"

# Local midnight in Vienna during summer time is 22:00 UTC, which is exactly how
# the API reports it: `"zeitpunktVon": "2026-09-19T22:00:00Z"`.
LOCAL_MIDNIGHT = datetime(2026, 9, 19, 22, tzinfo=UTC)


def _quarter_hours(start: datetime, count: int, wert: object = 0.25) -> list[dict]:
    """Build 15-minute Bewegungsdaten records as the API returns them."""
    return [
        {
            "wert": wert,
            "zeitpunktVon": (start + timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zeitpunktBis": (start + timedelta(minutes=15 * (i + 1))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "geschaetzt": False,
        }
        for i in range(count)
    ]


def _fake_client(values: list[dict], readings: list[dict] | None = None, auth_error: Exception | None = None):
    client = AsyncMock()
    client.authenticate.return_value = "token"
    client.authenticate.side_effect = auth_error
    client.fetch_bewegungsdaten.return_value = values
    client.fetch_meter_reading.return_value = readings if readings is not None else [{"messwert": 12345.678}]
    return client


async def _setup(hass, client):
    entry = make_entry(COOKIE_DATA)
    entry.add_to_hass(hass)
    with patch("custom_components.wiener_netze_smart_meter.WienerNetzeApiClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _fetch(hass, days: int = 7):
    return await hass.services.async_call(
        DOMAIN, SERVICE_FETCH_DATA, {"days": days}, blocking=True, return_response=True
    )


async def _total_statistics(hass) -> list[dict]:
    await async_wait_recording_done(hass)
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        LOCAL_MIDNIGHT - timedelta(days=1),
        LOCAL_MIDNIGHT + timedelta(days=1),
        {TOTAL_STATISTIC_ID},
        "hour",
        None,
        {"state", "sum"},
    )
    return stats.get(TOTAL_STATISTIC_ID, [])


def test_quarter_hours_are_summed_into_utc_hours():
    hourly = _aggregate_to_hourly(_quarter_hours(LOCAL_MIDNIGHT - timedelta(hours=1), 8))

    assert hourly == {LOCAL_MIDNIGHT - timedelta(hours=1): 1.0, LOCAL_MIDNIGHT: 1.0}


def test_timestamps_with_an_offset_land_in_the_same_utc_hour():
    hourly = _aggregate_to_hourly([{"wert": 1.5, "zeitpunktVon": "2026-09-20T00:00:00+02:00"}])

    assert hourly == {LOCAL_MIDNIGHT: 1.5}


@pytest.mark.parametrize("wert", ["n/a", "", [], {}, "nan", "inf", "-inf", float("nan")])
def test_a_non_numeric_value_is_skipped_not_raised(wert):
    values = _quarter_hours(LOCAL_MIDNIGHT, 4)
    values[1]["wert"] = wert

    assert _aggregate_to_hourly(values) == {LOCAL_MIDNIGHT: 0.75}


def test_records_without_value_or_timestamp_are_skipped():
    values = [{"wert": None, "zeitpunktVon": "2026-09-19T22:00:00Z"}, {"wert": 1.0}, {"wert": 1.0, "zeitpunktVon": "x"}]

    assert _aggregate_to_hourly(values) == {}


@pytest.mark.parametrize(("reading", "expected"), [({"messwert": 12.5}, 12.5), ({"messwert": "12.5"}, 12.5)])
def test_meter_reading_is_parsed(reading, expected):
    assert _parse_meter_reading(reading) == expected


@pytest.mark.parametrize(
    "reading", [{}, {"messwert": None}, {"messwert": "n/a"}, {"messwert": "nan"}, {"messwert": float("inf")}]
)
def test_an_unusable_meter_reading_is_none_not_zero(reading):
    """A missing counter value must not show up as a meter reading of 0 kWh."""
    assert _parse_meter_reading(reading) is None


async def test_fetch_imports_hourly_statistics(hass):
    await _setup(hass, _fake_client(_quarter_hours(LOCAL_MIDNIGHT, 8)))

    response = await _fetch(hass)

    assert response["success"] is True
    stats = await _total_statistics(hass)
    assert [s["state"] for s in stats] == [1.0, 1.0]


async def test_cumulative_sum_keeps_growing_across_local_midnight(hass):
    """The sum is one monotonically increasing series; it never resets at midnight.

    The Energy Dashboard derives per-day consumption from the sum's differences
    and groups by local day itself, so no reset is needed -- and the README must
    not claim one happens.
    """
    await _setup(hass, _fake_client(_quarter_hours(LOCAL_MIDNIGHT - timedelta(hours=2), 16)))

    await _fetch(hass)

    stats = await _total_statistics(hass)
    assert [s["sum"] for s in stats] == [1.0, 2.0, 3.0, 4.0]


async def test_a_later_fetch_continues_from_the_stored_sum(hass):
    client = _fake_client(_quarter_hours(LOCAL_MIDNIGHT, 4))
    await _setup(hass, client)
    await _fetch(hass)
    await async_wait_recording_done(hass)

    client.fetch_bewegungsdaten.return_value = _quarter_hours(LOCAL_MIDNIGHT + timedelta(hours=1), 4)
    await _fetch(hass)

    stats = await _total_statistics(hass)
    assert [s["sum"] for s in stats] == [1.0, 2.0]


@pytest.mark.parametrize("messwert", [None, "n/a", "nan"])
async def test_an_unusable_meter_reading_does_not_fail_a_successful_import(hass, messwert):
    """Before the guard, float(None) raised after the statistics were already written."""
    entry = await _setup(hass, _fake_client(_quarter_hours(LOCAL_MIDNIGHT, 4), readings=[{"messwert": messwert}]))

    response = await _fetch(hass)

    assert response["success"] is True
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data["meter_reading"] is None
    assert coordinator.data["stats_count"] == dict.fromkeys(ROLES, 1)


async def test_a_non_numeric_value_does_not_fail_the_import(hass):
    values = _quarter_hours(LOCAL_MIDNIGHT, 4)
    values[2]["wert"] = "n/a"
    await _setup(hass, _fake_client(values))

    response = await _fetch(hass)

    assert response["success"] is True
    assert [s["state"] for s in await _total_statistics(hass)] == [0.75]


async def test_a_meter_reading_api_error_is_tolerated(hass):
    client = _fake_client(_quarter_hours(LOCAL_MIDNIGHT, 4))
    client.fetch_meter_reading.side_effect = ApiError("HTTP 500")
    entry = await _setup(hass, client)

    response = await _fetch(hass)

    assert response["success"] is True
    assert hass.data[DOMAIN][entry.entry_id].data["meter_reading"] is None


async def test_expired_credentials_start_a_reauth_flow(hass):
    """A service-triggered fetch that fails to authenticate must surface a reauth.

    Core's `async_start_reauth_if_available` returns silently when the flow has no
    `async_step_reauth`; this asserts the flow now exists and gets started.
    """
    entry = await _setup(hass, _fake_client([], auth_error=AuthenticationError("cookie expired")))

    with pytest.raises(HomeAssistantError, match="cookie expired"):
        await _fetch(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [(f["context"]["source"], f["context"]["entry_id"]) for f in flows] == [(SOURCE_REAUTH, entry.entry_id)]
