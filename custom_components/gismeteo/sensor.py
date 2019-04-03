#
#  Copyright (c) 2019, Andrey "Limych" Khrolenok <andrey@khrolenok.ru>
#  Creative Commons BY-NC-SA 4.0 International Public License
#  (see LICENSE.md or https://creativecommons.org/licenses/by-nc-sa/4.0/)
#
"""
The Gismeteo component.

For more details about this platform, please refer to the documentation at
https://github.com/Limych/HomeAssistantComponents/
"""
import logging
import os

import voluptuous as vol
from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION, PLATFORM_SCHEMA)
from homeassistant.const import (
    ATTR_ATTRIBUTION, CONF_MONITORED_CONDITIONS, CONF_NAME, TEMP_CELSIUS)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import (
    ATTRIBUTION, DEFAULT_NAME, MIN_TIME_BETWEEN_UPDATES, CONF_CACHE_DIR,
    DEFAULT_CACHE_DIR)

REQUIREMENTS = []

_LOGGER = logging.getLogger(__name__)

CONF_FORECAST = 'forecast'
CONF_LANGUAGE = 'language'

PRECIPITATION_AMOUNT = (0, 2, 6, 16)

SENSOR_TYPES = {
    'weather': ['Condition', None],
    'temperature': ['Temperature', TEMP_CELSIUS],
    'wind_speed': ['Wind speed', 'm/s'],
    'wind_bearing': ['Wind bearing', '°'],
    'humidity': ['Humidity', '%'],
    'pressure': ['Pressure', 'hPa'],
    'clouds': ['Cloud coverage', '%'],
    'rain': ['Rain', 'mm'],
    'snow': ['Snow', 'mm'],
    'storm': ['Storm', None],
    'geomagnetic': ['Geomagnetic field', ''],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_FORECAST, default=False): cv.boolean,
})


def setup_platform(hass, config, add_entities,
                   discovery_info=None):
    """Set up the Gismeteo weather platform."""

    if None in (hass.config.latitude, hass.config.longitude):
        _LOGGER.error("Latitude or longitude not set in Home Assistant config")
        return
    latitude = round(hass.config.latitude, 6)
    longitude = round(hass.config.longitude, 6)

    name = config.get(CONF_NAME)
    forecast = config.get(CONF_FORECAST)
    cache_dir = config.get(CONF_CACHE_DIR, DEFAULT_CACHE_DIR)

    _LOGGER.debug("Initializing for coordinates %s, %s", latitude, longitude)

    from . import _gismeteo
    gm = _gismeteo.Gismeteo(params={
        'cache_dir': str(cache_dir) + '/gismeteo' if os.access(cache_dir, os.X_OK | os.W_OK) else None,
        'cache_time': MIN_TIME_BETWEEN_UPDATES.total_seconds(),
    })

    city = list(gm.cities_nearby(latitude, longitude, 1))[0]
    _LOGGER.debug("Nearby detected city is %s", city.get("name"))

    wd = _gismeteo.WeatherData(hass, gm, city.get("id"))

    dev = []
    for variable in config[CONF_MONITORED_CONDITIONS]:
        dev.append(GismeteoSensor(
            name, wd, variable, SENSOR_TYPES[variable][1]))

    if forecast:
        SENSOR_TYPES['forecast'] = ['Forecast', None]
        dev.append(GismeteoSensor(
            name, wd, 'forecast', SENSOR_TYPES['forecast'][1]))

    add_entities(dev, True)


class GismeteoSensor(Entity):
    """Implementation of an Gismeteo sensor."""

    def __init__(self, station_name, weather_data, sensor_type, temp_unit):
        """Initialize the sensor."""
        self.client_name = station_name
        self._name = SENSOR_TYPES[sensor_type][0]
        self._wd = weather_data
        self.temp_unit = temp_unit
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    def update(self):
        """Get the latest data from Gismeteo and updates the states."""
        self._wd.update()

        if self._wd.data is None:
            return

        data = self._wd.data['current']
        try:
            if self.type == 'weather':
                self._state = self._wd.condition()
            elif self.type == 'forecast':
                self._state = self._wd.forecast()[0][ATTR_FORECAST_CONDITION]
            elif self.type == 'temperature':
                self._state = self._wd.temperature()
            elif self.type == 'wind_speed':
                self._state = self._wd.wind_speed_ms()
            elif self.type == 'wind_bearing':
                self._state = self._wd.wind_bearing()
            elif self.type == 'humidity':
                self._state = self._wd.humidity()
            elif self.type == 'pressure':
                self._state = self._wd.pressure_hpa()
            elif self.type == 'clouds':
                self._state = int(round(data['cloudiness'] * 33.33, 0))
            elif self.type == 'rain':
                if data['precipitation']['type'] in [1, 3]:
                    self._state = round(data['precipitation']['amount']
                                        or PRECIPITATION_AMOUNT[data['precipitation']['intensity']], 0)
                    self._unit_of_measurement = SENSOR_TYPES['rain'][1]
                else:
                    self._state = 'not raining'
                    self._unit_of_measurement = ''
            elif self.type == 'snow':
                if data['precipitation']['type'] in [2, 3]:
                    self._state = round(data['precipitation']['amount']
                                        or PRECIPITATION_AMOUNT[data['precipitation']['intensity']], 0)
                    self._unit_of_measurement = SENSOR_TYPES['snow'][1]
                else:
                    self._state = 'not snowing'
                    self._unit_of_measurement = ''
            elif self.type == 'storm':
                self._state = data['storm']
            elif self.type == 'geomagnetic':
                self._state = int(data['gm'])
        except KeyError:
            self._state = None
            _LOGGER.warning("Condition is currently not available: %s", self.type)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement