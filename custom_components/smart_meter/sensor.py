"""Sensor platform for smart_meter."""
import logging
from datetime import timedelta
import requests
from .const import *
from datetime import datetime, timedelta

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import DEVICE_CLASS_POWER


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the smart_meter sensor platform."""
    token = entry.data["TOKEN"]
    interval = entry.data["INTERVAL"]
    user = entry.data["GP"]
    device = entry.data["DEVICE"]
    extraSmallIntervalEnabled = entry.data["15MIN_ENABLED"]
    coordinator = SmartMeterDataCoordinator(hass, token, interval, user, device, extraSmallIntervalEnabled)

    await coordinator.async_config_entry_first_refresh()
 
    async_add_entities([
        SmartMeterSensor(coordinator, "Smart Meter History", "smart_meter.history", "history"), 
        SmartMeterSensor(coordinator, "Smart Meter Reading", "smart_meter.readings", "meterReadings"), 
        SmartMeterSensor(coordinator, "Smart Meter Consumption Yesterday", "smart_meter.consumption_yesterday", "consumptionYesterday"),
        SmartMeterSensor(coordinator, "Smart Meter Consumption Day before Yesterday", "smart_meter.consumption_day_before_yesterday", "consumptionDayBeforeYesterday")
    ], True)

class SmartMeterDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching smart meter data."""

    def __init__(self, hass, token, interval, user, device, extraSmallIntervalEnabled):
        self._token = token 
        self._interval = timedelta(minutes=interval)
        self._access_token = None
        self._data = {}
        self._user = user
        self._device = device
        self._role = "V002" if extraSmallIntervalEnabled else "V001"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )

    async def _async_update_data(self):
        """Fetch the latest data from the API."""
        await self._get_access_token()
        if self._access_token:
            await self._get_consumption_history_data()
            await self._get_consumption_data()
            await self._get_meter_reading_data()

    async def _get_access_token(self):
        code = None
        try:
            def execute_request():
                auth_url = AUTHORIZATION_ENDPOINT
                auth_params = {
                    "client_id": CLIENT_ID,
                    "redirect_uri": ALLOWED_REDIRECT_URL,
                    "state": "9c3aa679-9415-4925-883d-4ea46fde391b",
                    "response_mode": "fragment",
                    "response_type": "code",
                    "scope": "openid",
                    "nonce": "c5016118-667d-4788-8856-2b67cfc95399",
                    "prompt": "none"
                }
                auth_cookies = {"KEYCLOAK_IDENTITY": self._token}
                session = requests.session()
                return session.get(auth_url, params=auth_params, cookies=auth_cookies, allow_redirects=False)
        
            response = await self.hass.async_add_executor_job(execute_request)

            if not response.headers.get("location"):
                _LOGGER.error(response.headers)
                raise UpdateFailed(f"Error getting code from authorization call!")
            
            code = response.headers.get("location").split("code=")[1]
        except Exception as e:
            raise UpdateFailed(f"Error getting access token: {e}")

        if not code:
            raise UpdateFailed("Failed to obtain code from authorization call.")

        try:
            def _execute_request():
                token_url = TOKEN_ENDPOINT
                token_payload = {
                    "code": code,
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": ALLOWED_REDIRECT_URL
                }
                session = requests.session()
                return session.post(token_url, data=token_payload)
        
            response = await self.hass.async_add_executor_job(_execute_request)
            self._access_token = response.json().get("access_token")
        except Exception as e:
            raise UpdateFailed(f"Error getting access token: {e}")

        if not self._access_token:
            raise UpdateFailed("Failed to obtain access token from token call.")

    async def _get_consumption_history_data(self):
        try:
            def _execute_data_request():
                api_url = "https://service.wienernetze.at/sm/api/user/messwerte/bewegungsdaten"
                headers = {"Authorization": f"Bearer {self._access_token}"}
                params = {
                    "geschaeftspartner": self._user,
                    "zaehlpunktnummer": self._device,
                    "rolle": self._role,
                    "zeitpunktBis": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "zeitpunktVon": (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "aggregat": "NONE"
                }
                session = requests.session()
                return session.get(api_url, headers=headers, params=params)
            

            response = await self.hass.async_add_executor_job(_execute_data_request)
            self._data["history"] = response.json().get("values")

        except Exception as e:
            raise UpdateFailed(f"Error getting power consumption data: {e}")

        if not self._data["history"]:
            raise UpdateFailed("Failed to obtain power consumption data.")
        
    async def _get_meter_reading_data(self):
        try:
            def _execute_data_request():
                api_url = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0/zaehlpunkt/meterReadings"
                headers = {"Authorization": f"Bearer {self._access_token}",
                           "X-Gateway-Apikey": "afb0be74-6455-44f5-a34d-6994223020ba"}
                session = requests.session()
                return session.get(api_url, headers=headers)
            

            response = await self.hass.async_add_executor_job(_execute_data_request)
            self._data["meterReadings"] = response.json().get("meterReadings")[0]

        except Exception as e:
            raise UpdateFailed(f"Error getting meterReadings data: {e}")

        if not self._data["meterReadings"]:
            raise UpdateFailed("Failed to obtain meterReadings data.")
        
    async def _get_consumption_data(self):
        try:
            def _execute_data_request():
                api_url = "https://api.wstw.at/gateway/WN_SMART_METER_PORTAL_API_B2C/1.0/zaehlpunkt/consumptions"
                headers = {"Authorization": f"Bearer {self._access_token}",
                           "X-Gateway-Apikey": "afb0be74-6455-44f5-a34d-6994223020ba"}
                session = requests.session()
                return session.get(api_url, headers=headers)
            

            response = await self.hass.async_add_executor_job(_execute_data_request)
            self._data["consumptionYesterday"] = response.json().get("consumptionYesterday")
            self._data["consumptionDayBeforeYesterday"] = response.json().get("consumptionDayBeforeYesterday")

        except Exception as e:
            raise UpdateFailed(f"Error getting consumption data: {e}")

        if not self._data["consumptionYesterday"]:
            raise UpdateFailed("Failed to obtain consumption data.")
        


class SmartMeterSensor(Entity):
    """Representation of the smart meter sensor."""

    def __init__(self, coordinator, name, id, data_keyword):
        """Initialize the sensor."""
        self._unit_of_measurement = "KWH"
        self._state = None
        self._coordinator = coordinator
        self._name = name
        self._id = id
        self._data_keword = data_keyword


    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name
    
    @property
    def unique_id(self):
        return self._id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement
    
    @property
    def icon(self):
        """Return the icon to use for device if any."""
        return "mdi:flash"  

    @property
    def device_class(self):
        """Return the device class."""
        return DEVICE_CLASS_POWER

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await self._coordinator.async_request_refresh()
        data = self._coordinator._data[self._data_keword]
        if not data:
            return

        if isinstance(data, list):
            self._state = float(data[0]["wert"])
        elif isinstance(data, dict):
            self._state = int(data["value"]) / 1000
        else:
            self._state = None
     
