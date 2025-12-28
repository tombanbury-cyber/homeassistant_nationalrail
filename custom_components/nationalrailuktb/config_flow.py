"""Config flow for National Rail UK integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant. data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .client import (
    NationalRailClient,
    NationalRailClientInvalidInput,
    NationalRailClientInvalidToken,
)
from .const import CONF_DESTINATIONS, CONF_STATION, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol. Schema(
    {
        vol.Required(CONF_TOKEN): str,
        vol.Required(CONF_STATION): str,
        vol.Optional(CONF_DESTINATIONS): str,
    }
)


async def validate_input(hass:  HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect. 

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # validate the token by calling a known line

    try:
        my_api = NationalRailClient(data[CONF_TOKEN], "WAT", ["CHK"])
        res = await my_api.async_get_data()
    except NationalRailClientInvalidToken as err:
        _LOGGER.exception(err)
        raise InvalidToken() from err

    # validate station input and get station name

    try:
        destinations_list = (
            data[CONF_DESTINATIONS]. split(",") 
            if data. get(CONF_DESTINATIONS) 
            else []
        )
        my_api = NationalRailClient(
            data[CONF_TOKEN], data[CONF_STATION], destinations_list
        )
        res = await my_api.async_get_data()
        station_name = res. get("station", data[CONF_STATION])
    except NationalRailClientInvalidInput as err:
        _LOGGER.exception(err)
        raise InvalidInput() from err

    # Return info that you want to store in the config entry. 
    if data. get(CONF_DESTINATIONS):
        return {
            "title": f'Train Schedule {station_name} -> {data["destinations"]}',
            "station_name": station_name,
        }
    else:
        return {
            "title": f'Train Schedule {station_name} (All Destinations)',
            "station_name":  station_name,
        }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for National Rail UK."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", 
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "station_help": "Enter a 3-letter station code (e.g., WAT for Waterloo, PAD for Paddington)"
                }
            )

        user_input[CONF_STATION] = user_input[CONF_STATION].strip().upper()
        if user_input. get(CONF_DESTINATIONS):
            user_input[CONF_DESTINATIONS] = (
                user_input[CONF_DESTINATIONS].strip().replace(" ", "").upper()
            )
        else:
            user_input[CONF_DESTINATIONS] = ""

        errors = {}

        try:
            info = await validate_input(self. hass, user_input)
        except InvalidToken: 
            errors["base"] = "invalid_token"
        except InvalidInput:
            errors["base"] = "invalid_station_input"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            # Show confirmation with human-readable station name
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "station_help": "Enter a 3-letter station code (e.g., WAT for Waterloo, PAD for Paddington)"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for National Rail UK."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Process the user input
            user_input[CONF_STATION] = user_input[CONF_STATION].strip().upper()
            if user_input.get(CONF_DESTINATIONS):
                user_input[CONF_DESTINATIONS] = (
                    user_input[CONF_DESTINATIONS].strip().replace(" ", "").upper()
                )
            else:
                user_input[CONF_DESTINATIONS] = ""

            errors = {}

            try:
                # Validate using the existing token
                token = self.config_entry. data.get(CONF_TOKEN)
                validate_data = {
                    CONF_TOKEN:  token,
                    CONF_STATION: user_input[CONF_STATION],
                    CONF_DESTINATIONS: user_input[CONF_DESTINATIONS],
                }
                info = await validate_input(self.hass, validate_data)
            except InvalidToken:
                errors["base"] = "invalid_token"
            except InvalidInput:
                errors["base"] = "invalid_station_input"
            except Exception:   # pylint: disable=broad-except
                _LOGGER. exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Update the config entry with new data
                self. hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_TOKEN:  token,
                        CONF_STATION: user_input[CONF_STATION],
                        CONF_DESTINATIONS: user_input[CONF_DESTINATIONS],
                    },
                    title=info["title"],
                )
                # Trigger reload
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self. async_create_entry(title="", data={})

            # Show form again with errors
            options_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_STATION,
                        default=self.config_entry.data.get(CONF_STATION),
                    ): str,
                    vol.Optional(
                        CONF_DESTINATIONS,
                        default=self.config_entry.data. get(CONF_DESTINATIONS, ""),
                    ): str,
                }
            )
            return self.async_show_form(
                step_id="init", 
                data_schema=options_schema, 
                errors=errors,
                description_placeholders={
                    "station_help":  "Enter a 3-letter station code (e.g., WAT for Waterloo, PAD for Paddington)",
                    "dest_help": "Optional:  Enter destination station codes separated by commas (e.g., CHK,VIC)"
                }
            )

        # Initial display of the form - get current station name for display
        current_station = self.config_entry.data.get(CONF_STATION)
        station_display = current_station
        
        # Try to get the human-readable name
        try:
            token = self.config_entry.data.get(CONF_TOKEN)
            destinations_list = (
                self. config_entry.data.get(CONF_DESTINATIONS, "").split(",")
                if self. config_entry.data.get(CONF_DESTINATIONS)
                else []
            )
            my_api = NationalRailClient(token, current_station, destinations_list)
            res = await my_api. async_get_data()
            station_display = f"{res.get('station', current_station)} ({current_station})"
        except Exception: 
            _LOGGER.debug("Could not fetch station name for display")

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_STATION,
                    default=self.config_entry.data.get(CONF_STATION),
                ): str,
                vol.Optional(
                    CONF_DESTINATIONS,
                    default=self.config_entry.data.get(CONF_DESTINATIONS, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", 
            data_schema=options_schema,
            description_placeholders={
                "current_station": station_display,
                "station_help": "Enter a 3-letter station code (e.g., WAT for Waterloo, PAD for Paddington)",
                "dest_help": "Optional: Enter destination station codes separated by commas (e.g., CHK,VIC)"
            }
        )


class InvalidToken(HomeAssistantError):
    """Error to indicate the Token is invalid."""


class InvalidInput(HomeAssistantError):
    """Error to indicate there is invalid user input."""
