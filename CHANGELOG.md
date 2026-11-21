# Changelog

## 0.1.0b1 - 2026-11-21

First beta.

- Integration `powerbill_forecast` with config and options flow
- Tariff presets for Thailand (PEA / MEA 1.1.1 and 1.1.2) and fully custom tiered tariffs
- Fuel adjustment (Ft) as a fixed value or from any sensor, service fee and VAT
- Billing cycle on any day of the month, utility meters and lifetime meters
- Month-end forecast that blends the cycle average with the last 7 days
- 10 sensors: forecast bill, current bill, previous cycle bill, cycle and forecast energy, tier, energy to next tier, price of the next kWh, average price, days left
- `custom:powerbill-forecast-card` with animated tier staircase, daily energy bars and bill details
