"""Constants for Powerbill Forecast."""

DOMAIN = "powerbill_forecast"
VERSION = "0.1.0b1"

CARD_FILE = "powerbill-forecast-card.js"
URL_FRONTEND = "/powerbill_forecast_static"

CONF_SOURCE = "source_entity"
CONF_METER_TYPE = "meter_type"
CONF_RESET_DAY = "reset_day"
CONF_TARIFF = "tariff"
CONF_TIERS = "tiers"
CONF_SERVICE_FEE = "service_fee"
CONF_VAT = "vat"
CONF_CURRENCY = "currency"
CONF_FT_ENTITY = "ft_entity"
CONF_FT_VALUE = "ft_value"

METER_CYCLE = "cycle"  # resets at the start of every billing cycle (utility meter)
METER_LIFETIME = "lifetime"  # keeps counting up forever (smart plug / energy meter total)

DEFAULT_NAME = "Powerbill Forecast"
DEFAULT_RESET_DAY = 1
DEFAULT_TARIFF = "pea_1_2"

UPDATE_MINUTES = 10
RECENT_DAYS = 7
