"""Render the README screenshots of the card with demo data (run by the screenshots workflow)."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
CARD = (ROOT / "custom_components/powerbill_forecast/frontend/powerbill-forecast-card.js").read_text()
sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_data import DEMO  # noqa: E402

_spec = importlib.util.spec_from_file_location("report", ROOT / "custom_components/powerbill_forecast/report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)

OUT = ROOT / "docs/images"
OUT.mkdir(parents=True, exist_ok=True)

SHOTS = [
    ("card.png", 620, ["top_tier"], True),
    ("card_mobile.png", 380, ["tier_two"], False),
    ("card_small_tariff.png", 380, ["small_tariff"], False),
]

PAGE = """<!DOCTYPE html><html><body style="background:#0d1117;margin:0;padding:16px;font-family:Roboto,Arial,sans-serif">
<script>customElements.define('ha-card', class extends HTMLElement {});</script>
<script>%CARD%</script>
<div id="wrap" style="width:%WIDTH%px"></div>
<script>
const demo = %DEMO%;
for (const key of %KEYS%) {
  const c = document.createElement('powerbill-forecast-card');
  c.setConfig({ entity: 'sensor.demo', animate: false, _now: demo.now });
  c.hass = { locale: { language: 'en' }, states: { 'sensor.demo': { attributes: { card_data: demo.cards[key] } } } };
  document.getElementById('wrap').appendChild(c);
  if (%OPEN%) c.shadowRoot.querySelector('details').open = true;
}
</script></body></html>"""


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, width, keys, open_details in SHOTS:
            page = await browser.new_page(viewport={"width": width + 32, "height": 900}, device_scale_factor=2, timezone_id="Asia/Bangkok")
            html = (
                PAGE.replace("%CARD%", CARD)
                .replace("%WIDTH%", str(width))
                .replace("%DEMO%", json.dumps(DEMO))
                .replace("%KEYS%", json.dumps(keys))
                .replace("%OPEN%", "true" if open_details else "false")
            )
            await page.set_content(html)
            await page.wait_for_timeout(2500)
            await page.locator("#wrap").screenshot(path=str(OUT / name))
            print("rendered", name)
        mail = report.build_report(DEMO["cards"]["top_tier"], "previous")["html"]
        page = await browser.new_page(viewport={"width": 680, "height": 900}, device_scale_factor=2)
        await page.set_content(mail)
        await page.screenshot(path=str(OUT / "report.png"), full_page=True)
        print("rendered report.png")
        await browser.close()


asyncio.run(main())
