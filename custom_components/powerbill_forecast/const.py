"""Constants for Powerbill Forecast."""

DOMAIN = "powerbill_forecast"
VERSION = "0.1.3"

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
CONF_FT_SOURCE = "ft_source"

FT_SOURCE_PEA = "pea"  # official PEA website (same Ft for PEA and MEA)
FT_SOURCE_ENTITY = "entity"
FT_SOURCE_FIXED = "fixed"

METER_CYCLE = "cycle"  # resets at the start of every billing cycle (utility meter)
METER_LIFETIME = "lifetime"  # keeps counting up forever (smart plug / energy meter total)

DEFAULT_NAME = "Powerbill Forecast"
DEFAULT_RESET_DAY = 1
DEFAULT_TARIFF = "pea_1_2"

UPDATE_MINUTES = 10
RECENT_DAYS = 7

FT_REFRESH_HOURS = 12
CLOSE_DELAY_HOURS = 2  # wait for the statistics of the last hour before closing a cycle
READING_WINDOW_DAYS = 5  # a meter reading this close to the cycle change replaces the automatic close

EVENT_FT_CHANGED = "powerbill_forecast_ft_changed"
EVENT_CYCLE_CLOSED = "powerbill_forecast_cycle_closed"
SERVICE_BUILD_REPORT = "build_report"
SERVICE_METER_READING = "meter_reading"
