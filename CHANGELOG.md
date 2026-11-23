# Changelog

## 0.1.1 - 2026-11-23

- **New Thai residential tariff** (valid from the September 2026 bills) in the PEA / MEA presets: first 200 kWh at 3.0000, 201-400 at 4.1584, from 401 at 4.3583 THB/kWh. Checked against real PEA bills to the satang
- **Bill report e-mail laid out like a paper electricity bill**: bill period, meter reading date, consumption, charges in the usual order (energy with tier lines, service charge, Ft, total, VAT), total amount to pay and a six-month usage history
- Usage history of the last cycles from the long-term statistics

## 0.1.0 - 2026-11-22

First stable release.

- Tiered electricity bills for Thailand (PEA / MEA 1.1.1 and 1.1.2) and fully custom tiered tariffs, with service fee and VAT
- Ft surcharge fetched automatically from the official PEA website (twice a day, last value kept when the page is down)
- Billing cycle on any day of the month, utility meters and lifetime meters
- Month-end forecast from the cycle average, the last 7 days and the previous cycle
- 11 sensors: forecast bill, current bill, previous cycle bill, Ft surcharge, cycle and forecast energy, tier, energy to next tier, price of the next kWh, average price, days left
- Finished cycle frozen as the bill, action `powerbill_forecast.build_report` and a blueprint that emails the monthly bill report
- `custom:powerbill-forecast-card` with animated tier staircase, daily energy bars and bill details

## 0.1.0b3 - 2026-11-21

- Daily energy of a cycle no longer includes the meter reading day of the next cycle (the recorder returned one day too many - extra bar in card and bill report)

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
