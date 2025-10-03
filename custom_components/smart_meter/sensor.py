import base64
import hashlib
import logging
import os
import requests
from dateutil.parser import isoparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import *

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=60)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the smart_meter sensor platform."""
    token = entry.data["TOKEN"]
    interval = entry.data["INTERVAL"]
    user = entry.data["GP"]
    device = entry.data["DEVICE"]
    extraSmallIntervalEnabled = entry.data["15MIN_ENABLED"]
    import_days = entry.data["IMPORT_DAYS"]

    coordinator = SmartMeterDataCoordinator(
        hass, token, interval, user, device, extraSmallIntervalEnabled, import_days
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([
        SmartMeterSensor(coordinator, f"Smart Meter Reading {device}", f"smart_meter.readings_{device}", "meterReadings")
    ], True)


class SmartMeterDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching smart meter data."""

    def __init__(self, hass, token, interval, user, device, extraSmallIntervalEnabled, import_days):
        self._token = token
        self._interval = timedelta(minutes=interval)
        self._access_token = None
        self._data = {}
        self._user = user
        self._device = device
        self._role = "V002" if extraSmallIntervalEnabled else "V001"
        self._import_days = import_days
        self._first_run = True
        SCAN_INTERVAL = self._interval

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    def generate_code_verifier(self):
        verifier = base64.urlsafe_b64encode(os.urandom(64)).decode("utf-8")
        return verifier.rstrip("=")

    def generate_code_challenge(self, verifier):
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("utf-8")
        return challenge.rstrip("=")

    async def _async_update_data(self):
        await self._get_access_token()
        if self._access_token:
            await self._get_meter_reading_data()
            await self._get_consumption_history_data()
            self._first_run = False

    async def _get_access_token(self):
        code = None
        code_verifier = self.generate_code_verifier()
        code_challenge = self.generate_code_challenge(code_verifier)

        try:
            def execute_request():
                auth_params = {
                    "client_id": CLIENT_ID,
                    "redirect_uri": ALLOWED_REDIRECT_URL,
                    "state": "static-state",
                    "response_mode": "fragment",
                    "response_type": "code",
                    "scope": "openid",
                    "nonce": "static-nonce",
                    "prompt": "none",
                    "code_challenge_method": "S256",
                    "code_challenge": code_challenge,
                }
                auth_cookies = {"KEYCLOAK_IDENTITY": self._token}
                session = requests.session()
                _LOGGER.debug(f"[AUTH REQUEST] URL={AUTHORIZATION_ENDPOINT} PARAMS={auth_params} COOKIES={auth_cookies}")
                resp = session.get(
                    AUTHORIZATION_ENDPOINT,
                    params=auth_params,
                    cookies=auth_cookies,
                    allow_redirects=False,
                )
                _LOGGER.debug(f"[AUTH RESPONSE] STATUS={resp.status_code} HEADERS={resp.headers} BODY={resp.text}")
                return resp

            response = await self.hass.async_add_executor_job(execute_request)
            if not response.headers.get("location"):
                raise UpdateFailed("Error getting code from authorization call!")
            code = response.headers.get("location").split("code=")[1]
            _LOGGER.debug(f"[AUTH SUCCESS] CODE={code}")
        except Exception as e:
            _LOGGER.exception("Exception during auth request")
            raise UpdateFailed(f"Error getting access token: {e}")

        if not code:
            raise UpdateFailed("Failed to obtain code from authorization call.")

        try:
            def _execute_request():
                token_payload = {
                    "code": code,
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": ALLOWED_REDIRECT_URL,
                    "code_verifier": code_verifier,
                }
                session = requests.session()
                _LOGGER.debug(f"[TOKEN REQUEST] URL={TOKEN_ENDPOINT} DATA={token_payload}")
                resp = session.post(TOKEN_ENDPOINT, data=token_payload)
                _LOGGER.debug(f"[TOKEN RESPONSE] STATUS={resp.status_code} BODY={resp.text}")
                return resp

            response = await self.hass.async_add_executor_job(_execute_request)
            self._access_token = response.json().get("access_token")
            _LOGGER.debug(f"[TOKEN SUCCESS] ACCESS_TOKEN={self._access_token}")
        except Exception as e:
            _LOGGER.exception("Exception during token request")
            raise UpdateFailed(f"Error getting access token: {e}")

        if not self._access_token:
            raise UpdateFailed("Failed to obtain access token from token call.")

    async def _get_meter_reading_data(self):
        """Fetch meter reading data for sensor state."""
        try:
            days = self._import_days if self._first_run else 2
            def _execute_data_request():
                api_url = (
                        "https://service.wienernetze.at/sm/api/user/messwerte/meterReading/"
                        + self._user + "/" + self._device
                        + "?datetimeFrom=" + (datetime.utcnow() - timedelta(days=days + 1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        + "&datetimeTo=" + datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
                )
                headers = {"Authorization": f"Bearer {self._access_token}"}
                session = requests.session()
                _LOGGER.debug(f"[METERREADING REQUEST] URL={api_url} HEADERS={headers}")
                resp = session.get(api_url, headers=headers)
                _LOGGER.debug(f"[METERREADING RESPONSE] STATUS={resp.status_code} BODY={resp.text}")
                return resp

            response = await self.hass.async_add_executor_job(_execute_data_request)
            self._data["meterReadings"] = response.json().get("zaehlwerke", [])[0].get("messwerte", [])
            values = response.json().get("zaehlwerke", [])[0].get("messwerte", [])
            if values:
                map = {}
                for v in values:
                    map[datetime.fromisoformat(v["zeitBis"]).date().isoformat()] = v["messwert"]
                self._data["meterReadingsPerDay"] = map
            _LOGGER.debug(f"[METERREADING SUCCESS] Retrieved {len(self._data['meterReadings'])} values")

        except Exception as e:
            _LOGGER.exception("Exception fetching MeterReadings")
            raise UpdateFailed(f"Error getting meterReadings data: {e}")

    async def _get_consumption_history_data(self):
        """Fetch 15-min consumption data, aggregate hourly, and insert into HA statistics."""
        try:
            days = self._import_days if self._first_run else 2
            def _execute_data_request():
                api_url = "https://service.wienernetze.at/sm/api/user/messwerte/bewegungsdaten"
                headers = {"Authorization": f"Bearer {self._access_token}"}
                params = {
                    "geschaeftspartner": self._user,
                    "zaehlpunktnummer": self._device,
                    "rolle": self._role,
                    "zeitpunktBis": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "zeitpunktVon": (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "aggregat": "NONE"
                }
                session = requests.session()
                _LOGGER.debug(f"[BEWEGUNGSDATEN REQUEST] URL={api_url} HEADERS={headers} PARAMS={params}")
                resp = session.get(api_url, headers=headers, params=params)
                _LOGGER.debug(f"[BEWEGUNGSDATEN RESPONSE] STATUS={resp.status_code} BODY={resp.text}")
                return resp

            response = await self.hass.async_add_executor_job(_execute_data_request)
            values = response.json().get("values", [])

            if not values:
                _LOGGER.warning("[BEWEGUNGSDATEN] No values returned")
                return

            hourly_consumption = defaultdict(float)
            hourly_consumption_cumulative = defaultdict(float)
            start_value = None
            for v in values:
                consumption_value = v.get("wert")
                consumption_date = v.get("zeitpunktVon")
                if consumption_value is None or consumption_date is None:
                    LOGGER.debug(f"Meter reading entry not valid {v}, skipping value")
                    continue

                ts = isoparse(consumption_date).astimezone(timezone.utc)
                ts_hour = ts.replace(minute=0, second=0, microsecond=0)

                if start_value is None:
                    prev_day = (ts.date() - timedelta(days=1)).isoformat()
                    previous_day_meter_value = self._data["meterReadingsPerDay"].get(prev_day)
                    if previous_day_meter_value is None:
                        _LOGGER.debug(f"No meter reading found for {prev_day}, skipping value")
                        continue
                    start_value = float(previous_day_meter_value)

                start_value += float(consumption_value)
                hourly_consumption_cumulative[ts_hour] = start_value
                hourly_consumption[ts_hour] += float(consumption_value)

            self.add_statistics("Strom Verbrauchsdaten", "consumption", hourly_consumption)
            self.add_statistics("Strom Verbrauchszähler", "consumption_counter", hourly_consumption_cumulative)

        except Exception as e:
            _LOGGER.exception("Exception fetching Bewegungsdaten")
            raise UpdateFailed(f"Error getting power consumption data: {e}")

    def add_statistics(self, name, stat_id, data):
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=name,
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:{stat_id}_{self._device}".lower(),
            unit_of_measurement="kWh",
        )

        if data:
            for hour, value in sorted(data.items()):
                _LOGGER.debug(f"[HOURLY AGGREGATION] Hour={hour} Sum={value:.3f} kWh")

            statistic_data = [StatisticData(start=dt, sum=value) for dt, value in sorted(data.items())]
            async_add_external_statistics(self.hass, metadata, statistic_data)
            _LOGGER.debug(f"[BEWEGUNGSDATEN SUCCESS] Inserted {len(statistic_data)} hourly values")


class SmartMeterSensor(Entity):
    """Representation of the smart meter sensor."""

    def __init__(self, coordinator, name, id, data_keyword):
        self._unit_of_measurement = "kWh"
        self._state = None
        self._coordinator = coordinator
        self._name = name
        self._id = id
        self._data_keyword = data_keyword

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._id

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def icon(self):
        return "mdi:flash"

    @property
    def device_class(self):
        return SensorDeviceClass.ENERGY

    async def async_update(self):
        await self._coordinator.async_request_refresh()
        data = self._coordinator._data.get(self._data_keyword)

        if isinstance(data, list) and len(data) > 0:
            if "messwert" in data[-1]:
                self._state = float(data[-1].get("messwert"))
            elif "wert" in data[-1]:
                self._state = float(data[-1].get("wert"))
