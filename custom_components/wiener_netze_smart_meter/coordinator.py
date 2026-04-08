"""DataUpdateCoordinator for Wiener Netze Smart Meter."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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

        now = datetime.now(UTC)
        von = (now - timedelta(days=self._fetch_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        bis = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        result: dict = {
            "last_import": now.isoformat(),
            "fetch_days": self._fetch_days,
            "meter_reading": None,
            "stats_count": {},
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

    def _insert_statistics(self, rolle: str, hourly: dict[datetime, float]) -> int:
        """Build monotonically increasing sums and insert as external statistics."""
        if not hourly:
            return 0

        role_name = ROLE_NAMES.get(rolle, rolle)
        zpn_suffix = self._zaehlpunktnummer[-8:]
        statistic_id = f"{DOMAIN}:{role_name}_{zpn_suffix}"

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
            unit_class="energy",
            name=f"Smart Meter {role_name.title()}",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement="kWh",
        )

        # Get last known cumulative sum from recorder
        last_stats = get_last_statistics(self.hass, 1, statistic_id, True, {"sum"})
        if statistic_id in last_stats and last_stats[statistic_id]:
            last_sum = last_stats[statistic_id][0]["sum"]
            last_start = datetime.fromtimestamp(last_stats[statistic_id][0]["start"], tz=UTC)
        else:
            last_sum = 0.0
            last_start = datetime.min.replace(tzinfo=UTC)

        # Build statistics: state=hourly value, sum=monotonically increasing
        cumulative = last_sum
        statistics: list[StatisticData] = []
        for hour_start in sorted(hourly):
            if hour_start <= last_start:
                continue
            value = hourly[hour_start]
            cumulative += value
            statistics.append(StatisticData(start=hour_start, state=value, sum=cumulative))

        if statistics:
            async_add_external_statistics(self.hass, metadata, statistics)
            _LOGGER.debug("Inserted %d external statistics for %s", len(statistics), statistic_id)

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
                ts = ts.replace(tzinfo=UTC)
        except ValueError:
            _LOGGER.debug("Could not parse timestamp: %s", zeitpunkt)
            continue

        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        hourly[hour_start] += float(wert)

    return dict(hourly)
