# Changelog

## 0.1.0b2 - 2026-11-21

- **Ft from the official PEA website**: new Ft source "Official PEA website" (default in Thailand), fetched twice a day, last value kept when the page is down, event `powerbill_forecast_ft_changed`
- New sensor **Ft surcharge** with period, source and last download
- **Monthly bill report**: the finished cycle is frozen as the bill, event `powerbill_forecast_cycle_closed`, action `powerbill_forecast.build_report` (subject, HTML, text) and blueprint to send it
- Card shows the Ft period
- Setups from 0.1.0b1 keep their Ft entity or fixed value - switch to the PEA website under Configure

## 0.1.0b1 - 2026-11-21

First beta.

- Integration `powerbill_forecast` with config and options flow
- Tariff presets for Thailand (PEA / MEA 1.1.1 and 1.1.2) and fully custom tiered tariffs
- Fuel adjustment (Ft) as a fixed value or from any sensor, service fee and VAT
- Billing cycle on any day of the month, utility meters and lifetime meters
- Month-end forecast that blends the cycle average with the last 7 days
- 10 sensors: forecast bill, current bill, previous cycle bill, cycle and forecast energy, tier, energy to next tier, price of the next kWh, average price, days left
- `custom:powerbill-forecast-card` with animated tier staircase, daily energy bars and bill details
