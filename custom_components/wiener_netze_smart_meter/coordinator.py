"""DataUpdateCoordinator for Wiener Netze Smart Meter."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_client import ApiError, AuthenticationError, WienerNetzeApiClient
from .const import (
    CONF_GESCHAEFTSPARTNER,
    CONF_ZAEHLPUNKTNUMMER,
    DEFAULT_FETCH_DAYS,
    DOMAIN,
    ROLE_NAMES,
    ROLES,
)

_LOGGER = logging.getLogger(__name__)


class SmartMeterCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator that fetches smart meter data and inserts statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: WienerNetzeApiClient,
    ) -> None:
        self._client = client
        self._geschaeftspartner = entry.data[CONF_GESCHAEFTSPARTNER]
        self._zaehlpunktnummer = entry.data[CONF_ZAEHLPUNKTNUMMER]
        self._fetch_days = DEFAULT_FETCH_DAYS

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # No automatic polling — triggered via service action
        )

    async def async_fetch(self, days: int) -> None:
        """Fetch data for the given number of days and update sensors."""
        self._fetch_days = days
        await self.async_refresh()

    async def _async_update_data(self) -> dict:
        """Authenticate, fetch data, aggregate, and insert statistics."""
        try:
            access_token = await self._client.authenticate()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        now = datetime.now(timezone.utc)
        von = (now - timedelta(days=self._fetch_days)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        bis = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        result: dict = {
            "last_import": now.isoformat(),
            "fetch_days": self._fetch_days,
            "meter_reading": None,
            "stats_count": {},
            "daily_total": {},
        }

        # Fetch and insert statistics for each role
        for rolle in ROLES:
            try:
                values = await self._client.fetch_bewegungsdaten(
                    access_token,
                    self._geschaeftspartner,
                    self._zaehlpunktnummer,
                    rolle,
                    von,
                    bis,
                )
            except ApiError as err:
                _LOGGER.warning("Failed to fetch %s: %s", rolle, err)
                result["stats_count"][rolle] = 0
                continue

            if not values:
                _LOGGER.info("No data returned for rolle=%s", rolle)
                result["stats_count"][rolle] = 0
                continue

            hourly = _aggregate_to_hourly(values)
            count = self._insert_statistics(rolle, hourly)
            result["stats_count"][rolle] = count

            # Store the most recent day's total for the sensor entity
            if hourly:
                latest_day = max(hourly).strftime("%Y-%m-%d")
                result["daily_total"][rolle] = sum(
                    v for h, v in hourly.items()
                    if h.strftime("%Y-%m-%d") == latest_day
                )
            _LOGGER.info(
                "Inserted %d hourly statistics for %s (%s)",
                count,
                ROLE_NAMES.get(rolle, rolle),
                rolle,
            )

        # Fetch meter reading
        try:
            readings = await self._client.fetch_meter_reading(
                access_token,
                self._geschaeftspartner,
                self._zaehlpunktnummer,
                von,
                bis,
            )
            if readings:
                latest = readings[-1]
                result["meter_reading"] = float(latest.get("messwert", 0))
                _LOGGER.info("Latest meter reading: %s kWh", result["meter_reading"])
        except ApiError as err:
            _LOGGER.warning("Failed to fetch meter reading: %s", err)

        return result

    def _insert_statistics(
        self, rolle: str, hourly: dict[datetime, float]
    ) -> int:
        """Build cumulative sums per day and import as entity-linked statistics."""
        if not hourly:
            return 0

        role_name = ROLE_NAMES.get(rolle, rolle)
        zpn = self._zaehlpunktnummer

        # Look up the sensor entity_id to link statistics to it
        entity_registry = er.async_get(self.hass)
        unique_id = f"{DOMAIN}_{role_name}_{zpn}"
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if not entity_id:
            _LOGGER.warning(
                "Entity not found for unique_id=%s, skipping statistics", unique_id
            )
            return 0

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            name=f"Smart Meter {role_name.title()}",
            source="recorder",
            statistic_id=entity_id,
            unit_of_measurement="kWh",
        )

        # Group hours by day, cumulative sum resets each day
        days: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for hour_start, value in sorted(hourly.items()):
            day_key = hour_start.strftime("%Y-%m-%d")
            days[day_key].append((hour_start, value))

        statistics: list[StatisticData] = []
        for day_key in sorted(days):
            cumulative = 0.0
            for hour_start, value in days[day_key]:
                cumulative += value
                statistics.append(StatisticData(start=hour_start, sum=cumulative))

        if statistics:
            async_import_statistics(self.hass, metadata, statistics)
            _LOGGER.debug(
                "Imported %d statistics for entity %s", len(statistics), entity_id
            )

        return len(statistics)


def _aggregate_to_hourly(values: list[dict]) -> dict[datetime, float]:
    """Aggregate 15-min interval values to hourly sums."""
    hourly: dict[datetime, float] = defaultdict(float)

    for v in values:
        wert = v.get("wert")
        zeitpunkt = v.get("zeitpunktVon")
        if wert is None or zeitpunkt is None:
            continue

        try:
            ts = datetime.fromisoformat(zeitpunkt)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            _LOGGER.debug("Could not parse timestamp: %s", zeitpunkt)
            continue

        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        hourly[hour_start] += float(wert)

    return dict(hourly)
