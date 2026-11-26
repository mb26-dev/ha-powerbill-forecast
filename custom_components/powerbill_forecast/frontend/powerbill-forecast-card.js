/* Powerbill Forecast card - animated tier staircase, live bill and month-end forecast. */
const PBF_VERSION = "0.1.5";

const PALETTE = ["#22d3ee", "#2dd4bf", "#4ade80", "#facc15", "#fb923c", "#f97316", "#ef4444"];

function tierColor(i, n) {
  if (n <= 1) return PALETTE[0];
  const t = i / (n - 1);
  const pos = t * (PALETTE.length - 1);
  const a = Math.floor(pos);
  const b = Math.min(PALETTE.length - 1, a + 1);
  const f = pos - a;
  const ca = PALETTE[a].match(/\w\w/g).map((h) => parseInt(h, 16));
  const cb = PALETTE[b].match(/\w\w/g).map((h) => parseInt(h, 16));
  return "#" + ca.map((v, k) => Math.round(v + (cb[k] - v) * f).toString(16).padStart(2, "0")).join("");
}

// card_data is rendered as markup: apart from a few text fields every value must be a number
const TEXT_KEYS = new Set(["name", "tariff", "tariff_key", "currency", "symbol", "ft_period", "period", "fetched", "changed", "source", "cycle_start", "cycle_end", "date", "error"]);
const cleanData = (v, key = "") => {
  if (Array.isArray(v)) return v.map((x) => cleanData(x, key));
  if (v && typeof v === "object") { const o = {}; for (const k of Object.keys(v)) o[k] = cleanData(v[k], k); return o; }
  if (typeof v === "string" && !TEXT_KEYS.has(key)) { const n = Number(v); return Number.isFinite(n) ? n : null; }
  return v;
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class PowerbillForecastCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("powerbill-forecast-card-editor");
  }

  static getStubConfig(hass) {
    const ent = Object.keys(hass.states).find((e) => hass.states[e].attributes && hass.states[e].attributes.card_data);
    return { entity: ent || "" };
  }

  setConfig(config) {
    this._config = { show_daily: true, show_breakdown: true, show_chips: true, animate: true, ...config };
    this._stamp = null;
    if (this.shadowRoot) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const data = this._data();
    const stamp = data ? data.updated + "|" + data.kwh : "none";
    if (stamp !== this._stamp) {
      this._stamp = stamp;
      this._render();
    }
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _entityId() {
    if (this._config.entity) return this._config.entity;
    const hass = this._hass;
    return Object.keys(hass.states).find((e) => hass.states[e].attributes && hass.states[e].attributes.card_data);
  }

  _data() {
    if (!this._hass) return null;
    const id = this._entityId();
    const st = id && this._hass.states[id];
    if (!st || !st.attributes || !st.attributes.card_data) return null;
    if (this._rawData !== st.attributes.card_data) { this._rawData = st.attributes.card_data; this._clean = cleanData(this._rawData); }
    return this._clean;
  }

  _lang() {
    return (this._hass && this._hass.locale && this._hass.locale.language) || navigator.language || "en";
  }

  _num(v, d = 2) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    return new Intl.NumberFormat(this._lang(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  }

  _money(v, d = 2, html = true) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const raw = String(this._data()?.symbol || "");
    const s = html ? esc(raw) : raw; // the symbol can be any text the user typed - never raw into innerHTML
    return raw.length <= 2 ? s + this._num(v, d) : this._num(v, d) + " " + s;
  }

  _date(iso, opts = { day: "numeric", month: "short" }) {
    const d = new Date(iso);
    return isNaN(d) ? "–" : new Intl.DateTimeFormat(this._lang(), opts).format(d);
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const d = this._data();
    if (!d) {
      this.shadowRoot.innerHTML = `${this._style()}<ha-card><div class="empty">⚡ Powerbill Forecast: no data yet.<br><small>Add the integration under Settings → Devices & services, or set <code>entity</code> to the "Forecast bill" sensor.</small></div></ha-card>`;
      return;
    }
    const firstPaint = !this._painted;
    this._painted = true;
    const b = d.bill;
    const fb = d.forecast_bill;
    const n = d.tiers.length;
    const curColor = tierColor(b.current_tier - 1, n);
    const fcColor = tierColor(fb.current_tier - 1, n);
    const delta = d.previous_total ? ((fb.total - d.previous_total) / d.previous_total) * 100 : null;
    const fc = d.forecast;
    const pct = Math.min(100, (fc.days_elapsed / fc.days_total) * 100);
    const title = this._config.title || "Powerbill Forecast";

    const nextChip =
      b.kwh_to_next_tier === null
        ? `<span class="chip hot">🔥 Top tier reached</span>`
        : `<span class="chip"><b>${this._num(b.kwh_to_next_tier, 1)} kWh</b> to tier ${b.current_tier + 1}${d.days_to_next_tier !== null ? ` · ~${this._num(d.days_to_next_tier, 1)} d` : ""}</span>`;

    this.shadowRoot.innerHTML = `${this._style()}
      <ha-card>
        <div class="glow" style="--c:${curColor}"></div>
        <div class="head">
          <div class="title"><span class="bolt">⚡</span>${esc(title)}</div>
          <div class="tariff">${esc(d.tariff)}</div>
        </div>

        <div class="hero">
          <div class="box">
            <div class="lbl">Bill so far</div>
            <div class="big" data-count="${b.total}">${this._money(b.total)}</div>
            <div class="sub">${this._num(d.kwh, 1)} kWh · <span style="color:${curColor}">Tier ${b.current_tier}/${n}</span></div>
          </div>
          <div class="arrow"><svg viewBox="0 0 40 24"><path d="M2 12h30M24 4l10 8-10 8" /></svg></div>
          <div class="box fc">
            <div class="lbl">Forecast</div>
            <div class="big" style="color:${fcColor};text-shadow:0 0 18px ${fcColor}66" data-count="${fb.total}">${this._money(fb.total)}</div>
            <div class="sub">${this._num(fc.kwh, 0)} kWh${
              delta === null ? "" : ` · <span class="${delta > 0 ? "up" : "down"}">${delta > 0 ? "▲" : "▼"} ${this._num(Math.abs(delta), 0)}%</span>`
            }</div>
          </div>
        </div>

        <div class="cycle">
          <div class="cyc-txt"><span>${this._date(d.cycle_start)} → ${this._date(d.cycle_end)}</span><span><b>${this._num(fc.days_remaining, 1)}</b> days left</span></div>
          <div class="bar"><div class="fill" style="width:${pct}%;background:linear-gradient(90deg,${tierColor(0, n)},${curColor})"><i style="background:${curColor};box-shadow:0 0 10px ${curColor}"></i></div></div>
        </div>

        ${this._stairs(d)}

        ${
          this._config.show_chips
            ? `<div class="chips">
            <span class="chip">Next kWh <b style="color:${curColor}">${this._money(b.marginal_price, 2)}</b></span>
            ${nextChip}
            <span class="chip">Ø <b>${this._money(b.average_price, 2)}</b>/kWh</span>
            ${d.ft ? `<span class="chip" title="${esc(d.ft_info && d.ft_info.source === "pea" ? "Official PEA website" : "")}">Ft <b>${this._num(d.ft, 4)}</b>${d.ft_period ? ` · ${esc(d.ft_period)}` : ""}</span>` : ""}
          </div>`
            : ""
        }

        ${this._config.show_daily ? this._dailyChart(d) : ""}
        ${this._config.show_breakdown ? this._breakdown(d) : ""}
        ${
          d.previous_total
            ? `<div class="foot">Last cycle: <b>${this._money(d.previous_total)}</b> · ${this._num(d.previous_kwh, 0)} kWh</div>`
            : ""
        }
      </ha-card>`;

    if (firstPaint && this._config.animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) this._countUp();
  }

  _countUp() {
    this.shadowRoot.querySelectorAll("[data-count]").forEach((el) => {
      const target = parseFloat(el.dataset.count);
      if (isNaN(target)) return;
      const t0 = performance.now();
      const dur = 1100;
      const step = (t) => {
        const p = Math.min(1, (t - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        el.textContent = this._money(target * e, 2, false);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  /* ---------------------------------------------------------------- staircase */
  _stairs(d) {
    const n = d.tiers.length;
    const W = 640;
    const H = 250;
    const mx = 14;
    const dx = 16;
    const dy = 12;
    const base = H - 8;
    const sw = (W - 2 * mx - dx) / n;
    const rates = d.tiers.map((t) => t.rate);
    const rMin = Math.min(...rates);
    const rMax = Math.max(...rates);
    const kwh = d.kwh;
    const fkwh = d.forecast.kwh;
    const lastFrom = n > 1 ? d.tiers[n - 2].to : 0;
    const lastSpan = Math.max(lastFrom * 0.25, (Math.max(kwh, fkwh) - lastFrom) * 1.2, 50);

    const steps = d.tiers.map((t, i) => {
      const from = i === 0 ? 0 : d.tiers[i - 1].to;
      const to = t.to === null ? from + lastSpan : t.to;
      const hRate = rMax > rMin ? (t.rate - rMin) / (rMax - rMin) : 0;
      const h = 46 + hRate * 120 + i * (60 / Math.max(1, n - 1)) * 0.5;
      return { i, from, to, x: mx + i * sw, y: base - h, h, color: tierColor(i, n) };
    });

    const posX = (v) => {
      for (const s of steps) {
        if (v <= s.to || s.i === n - 1) return s.x + Math.max(0, Math.min(1, (v - s.from) / (s.to - s.from))) * sw;
      }
      return mx;
    };
    const stepAt = (v) => steps.find((s) => v <= s.to) || steps[n - 1];

    let defs = "";
    let blocks = "";
    steps.forEach((s) => {
      const used = Math.max(0, Math.min(kwh, s.to) - s.from);
      const fUsed = Math.max(0, Math.min(fkwh, s.to) - s.from);
      const fw = (used / (s.to - s.from)) * sw;
      const ffw = (fUsed / (s.to - s.from)) * sw;
      const active = d.bill.current_tier === s.i + 1;
      const id = `s${s.i}`;
      defs += `
        <clipPath id="c${id}"><rect x="${s.x}" y="${s.y}" width="${sw}" height="${s.h}" rx="3"/></clipPath>
        <linearGradient id="g${id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="${s.color}" stop-opacity=".95"/>
          <stop offset="1" stop-color="${s.color}" stop-opacity=".35"/>
        </linearGradient>`;
      blocks += `
        <g class="step ${active ? "active" : ""}" style="--c:${s.color}">
          <polygon class="top" points="${s.x},${s.y} ${s.x + dx},${s.y - dy} ${s.x + sw + dx},${s.y - dy} ${s.x + sw},${s.y}"
            fill="${s.color}" fill-opacity="${fw > 0 ? 0.55 : 0.12}" stroke="${s.color}"/>
          ${
            s.i === n - 1
              ? `<polygon class="side" points="${s.x + sw},${s.y} ${s.x + sw + dx},${s.y - dy} ${s.x + sw + dx},${base - dy} ${s.x + sw},${base}" fill="${s.color}" fill-opacity=".12" stroke="${s.color}"/>`
              : ""
          }
          <rect class="front" x="${s.x}" y="${s.y}" width="${sw}" height="${s.h}" rx="3" fill="#0b1220" stroke="${s.color}"/>
          <g clip-path="url(#c${id})">
            ${ffw > fw ? `<rect class="ghost" x="${s.x + fw}" y="${s.y}" width="${ffw - fw}" height="${s.h}" fill="${s.color}" fill-opacity=".16"/>` : ""}
            ${
              fw > 0
                ? `<rect x="${s.x}" y="${s.y}" width="${fw}" height="${s.h}" fill="url(#g${id})"/>
                   <rect class="shine" x="${s.x - 60}" y="${s.y}" width="40" height="${s.h}" fill="url(#shine)">
                     <animate attributeName="x" from="${s.x - 60}" to="${s.x + Math.max(fw, 40)}" dur="${2.4 + s.i * 0.3}s" repeatCount="indefinite"/>
                   </rect>`
                : ""
            }
          </g>
          ${ffw > fw ? `<rect x="${s.x + fw}" y="${s.y + 1}" width="${ffw - fw}" height="${s.h - 2}" fill="none" stroke="${s.color}" stroke-dasharray="5 4" class="dash"/>` : ""}
        </g>`;
    });

    // particle path: along the step tops up to the current position
    const cs = stepAt(kwh);
    const cx = posX(kwh);
    let path = `M ${steps[0].x} ${base - 2}`;
    for (const s of steps) {
      if (s.i > cs.i) break;
      path += ` L ${s.x} ${s.y - 4}`;
      if (s.i < cs.i) path += ` L ${s.x + sw} ${s.y - 4}`;
      else path += ` L ${cx} ${s.y - 4}`;
    }
    const particles = Array.from({ length: 7 }, (_, k) =>
      `<circle opacity="0" r="${k % 3 === 0 ? 3 : 2}" fill="${k % 2 ? "#fff" : cs.color}" filter="url(#blur)">
        <animateMotion dur="3.2s" begin="${(k * 3.2) / 7}s" repeatCount="indefinite" path="${path}"/>
        <animate attributeName="opacity" values="0;1;1;0" dur="3.2s" begin="${(k * 3.2) / 7}s" repeatCount="indefinite"/>
      </circle>`
    ).join("");

    const fs = stepAt(fkwh);
    const fx = posX(fkwh);
    const marker = `
      <g class="marker">
        <line x1="${cx}" y1="${cs.y - 6}" x2="${cx}" y2="${cs.y - 40}" stroke="${cs.color}" stroke-width="2"/>
        <circle cx="${cx}" cy="${cs.y - 4}" r="5" fill="${cs.color}" class="pulse"/>
        <path class="zap" d="M ${cx + 4} ${cs.y - 72} l -10 18 h 8 l -6 16 l 14 -21 h -8 l 6 -13 z" fill="#fde047"/>
        <rect x="${Math.min(W - 98, Math.max(2, cx - 46))}" y="${cs.y - 104}" width="92" height="26" rx="13" fill="#0b1220" stroke="${cs.color}"/>
        <text x="${Math.min(W - 52, Math.max(48, cx))}" y="${cs.y - 86}" text-anchor="middle" class="mtxt">${this._num(kwh, kwh < 1000 ? 1 : 0)} kWh</text>
      </g>
      ${
        fkwh > kwh + 0.5
          ? `<g class="fmark">
              <line x1="${fx}" y1="${fs.y - 2}" x2="${fx}" y2="${fs.y - 26}" stroke="${fs.color}" stroke-dasharray="3 3" stroke-width="2"/>
              <path d="M ${fx} ${fs.y - 26} l 18 6 l -18 6 z" fill="${fs.color}" fill-opacity=".85"/>
            </g>`
          : ""
      }`;

    const legend = steps
      .map((s, i) => {
        const t = d.tiers[i];
        const range = t.to === null ? `${this._num(s.from, 0)}+` : `${this._num(s.from === 0 ? 0 : s.from + 1, 0)}–${this._num(t.to, 0)}`;
        const active = d.bill.current_tier === i + 1;
        return `<div class="lg ${active ? "on" : ""}" style="--c:${s.color}"><span>${range}</span><b>${this._money(t.rate, n > 4 ? 2 : 4)}</b></div>`;
      })
      .join("");

    return `
      <div class="stairs">
        <svg viewBox="0 -60 ${W} ${H + 60}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Tier staircase">
          <defs>
            ${defs}
            <linearGradient id="shine" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
            <filter id="blur"><feGaussianBlur stdDeviation="1.2"/></filter>
            <filter id="neon" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          </defs>
          <g filter="url(#neon)">${blocks}</g>
          ${particles}
          ${marker}
        </svg>
        <div class="legend" style="grid-template-columns:repeat(${n},1fr);padding:0 ${((mx + dx / 2) / W) * 100}% 0 ${(mx / W) * 100}%">${legend}</div>
      </div>`;
  }

  /* ---------------------------------------------------------------- daily bars */
  _dailyChart(d) {
    const start = new Date(d.cycle_start);
    const days = Math.round(d.forecast.days_total);
    if (!days || !d.daily) return "";
    const byDate = Object.fromEntries(d.daily.map((x) => [x.date, x.kwh]));
    const today = (this._config._now ? new Date(this._config._now) : new Date()).toLocaleDateString("en-CA");
    const rate = d.forecast.daily_rate || 0;
    const n = d.tiers.length;
    const items = [];
    let cum = 0;
    let past = true;
    for (let k = 0; k < days; k++) {
      const dt = new Date(start.getTime() + k * 86400000 + 43200000);
      const key = dt.toLocaleDateString("en-CA");
      const isToday = key === today;
      let v = byDate[key];
      let future = false;
      if (v === undefined) {
        if (past && !isToday && key < today) v = 0;
        else {
          future = true;
          v = rate;
        }
      }
      if (isToday) past = false;
      cum += v;
      let tier = n - 1;
      for (let t = 0; t < n; t++) if (d.tiers[t].to === null || cum <= d.tiers[t].to) { tier = t; break; }
      items.push({ dt, v, future, isToday, color: tierColor(tier, n) });
    }
    const max = Math.max(...items.map((x) => x.v), 1);
    const bars = items
      .map(
        (x) =>
          `<div class="db ${x.future ? "fut" : ""} ${x.isToday ? "today" : ""}" title="${this._date(x.dt.toISOString(), { weekday: "short", day: "numeric", month: "short" })}: ${this._num(x.v, 1)} kWh${x.future ? " (forecast)" : ""}" style="--c:${x.color};--h:${Math.max(3, (x.v / max) * 100)}%"><i></i></div>`
      )
      .join("");
    return `
      <div class="daily">
        <div class="sec"><span>Daily energy</span><span>Ø ${this._num(rate, 1)} kWh/day${d.recent_daily ? ` · last 7 d ${this._num(d.recent_daily, 1)}` : ""}</span></div>
        <div class="dbars" style="grid-template-columns:repeat(${items.length},1fr)">${bars}</div>
      </div>`;
  }

  /* ---------------------------------------------------------------- breakdown */
  _breakdown(d) {
    const n = d.tiers.length;
    const rows = d.bill.tiers
      .map((t, i) => {
        const f = d.forecast_bill.tiers[i];
        if (!t.kwh && !f.kwh) return "";
        return `<tr><td><i class="dot" style="background:${tierColor(i, n)}"></i>Tier ${i + 1} <small>${this._money(t.rate, 4)}</small></td>
          <td>${this._num(t.kwh, 1)}</td><td>${this._money(t.cost)}</td><td class="f">${this._num(f.kwh, 1)}</td><td class="f">${this._money(f.cost)}</td></tr>`;
      })
      .join("");
    const line = (label, a, b) => `<tr><td>${label}</td><td></td><td>${this._money(a)}</td><td class="f"></td><td class="f">${this._money(b)}</td></tr>`;
    return `
      <details class="bd">
        <summary>Bill details</summary>
        <div class="tw"><table>
          <thead><tr><th></th><th>kWh</th><th>Now</th><th class="f">kWh</th><th class="f">Forecast</th></tr></thead>
          <tbody>
            ${rows}
            ${line("Energy", d.bill.energy, d.forecast_bill.energy)}
            ${d.ft ? line(`Ft <small>${this._num(d.ft, 4)}/kWh</small>`, d.bill.ft, d.forecast_bill.ft) : ""}
            ${line("Service fee", d.bill.service_fee, d.forecast_bill.service_fee)}
            ${d.vat ? line(`VAT ${this._num(d.vat, 0)}%`, d.bill.vat, d.forecast_bill.vat) : ""}
            <tr class="tot"><td>Total</td><td>${this._num(d.bill.kwh, 1)}</td><td>${this._money(d.bill.total)}</td><td class="f">${this._num(d.forecast_bill.kwh, 1)}</td><td class="f">${this._money(d.forecast_bill.total)}</td></tr>
          </tbody>
        </table></div>
      </details>`;
  }

  _style() {
    return `<style>
      :host { container-type: inline-size; display: block; }
      ha-card { display: block; position: relative; overflow: hidden; padding: 14px 14px 12px; color: #e2e8f0;
        background: radial-gradient(120% 90% at 0% 0%, #13213a 0%, #0a1020 55%, #070b16 100%);
        border: 1px solid rgba(56,189,248,.25); }
      .glow { position: absolute; inset: -40% -20% auto auto; width: 70%; height: 90%; pointer-events: none;
        background: radial-gradient(circle, color-mix(in srgb, var(--c) 30%, transparent), transparent 65%); filter: blur(10px); }
      .empty { padding: 18px; text-align: center; }
      .head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 10px; position: relative; }
      .title { font-weight: 700; font-size: 16px; letter-spacing: .3px; white-space: nowrap; }
      .bolt { color: #fde047; margin-right: 6px; text-shadow: 0 0 10px #fde047; animation: flick 3s infinite; }
      .tariff { font-size: 11px; color: #94a3b8; text-align: right; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .hero { display: grid; grid-template-columns: minmax(0,1fr) 34px minmax(0,1fr); align-items: center; gap: 6px; position: relative; }
      .box { background: rgba(15,23,42,.65); border: 1px solid rgba(148,163,184,.15); border-radius: 14px; padding: 10px 12px; min-width: 0; }
      .box.fc { border-color: rgba(250,204,21,.25); }
      .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; }
      .big { font-size: clamp(20px, 7cqi, 30px); font-weight: 800; line-height: 1.15; margin: 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
      .sub { font-size: 12px; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .up { color: #f87171; } .down { color: #4ade80; }
      .arrow svg { width: 34px; height: 20px; fill: none; stroke: #fde047; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round;
        stroke-dasharray: 6 4; animation: flow 1s linear infinite; filter: drop-shadow(0 0 4px #fde047); }
      .cycle { margin: 12px 2px 4px; }
      .cyc-txt { display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; margin-bottom: 5px; }
      .cyc-txt b { color: #e2e8f0; }
      .bar { height: 6px; border-radius: 3px; background: rgba(148,163,184,.15); overflow: visible; }
      .fill { position: relative; height: 100%; border-radius: 3px; }
      .fill i { position: absolute; right: -4px; top: -3px; width: 12px; height: 12px; border-radius: 50%; animation: pulse 1.8s infinite; }
      .stairs { margin-top: 4px; }
      .stairs svg { width: 100%; height: auto; display: block; overflow: visible; }
      .step .front { stroke-width: 1.6; }
      .step .top, .step .side { stroke-width: 1.2; }
      .step.active .front { stroke-width: 2.6; animation: neon 1.8s ease-in-out infinite; }
      .dash { stroke-width: 1.5; animation: flow 1.2s linear infinite; }
      .pulse { animation: pulse 1.6s infinite; transform-box: fill-box; transform-origin: center; }
      .zap { animation: flick 2.2s infinite; filter: drop-shadow(0 0 6px #fde047); }
      .mtxt { fill: #f8fafc; font-size: 14px; font-weight: 700; font-family: inherit; }
      .legend { display: grid; gap: 2px; margin-top: 2px; }
      .lg { text-align: center; font-size: 11px; color: #94a3b8; line-height: 1.25; padding: 3px 0; border-top: 2px solid color-mix(in srgb, var(--c) 45%, transparent); min-width: 0; }
      .lg span { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .lg b { color: var(--c); font-weight: 700; white-space: nowrap; }
      .lg.on { color: #f1f5f9; border-top-color: var(--c); background: linear-gradient(180deg, color-mix(in srgb, var(--c) 18%, transparent), transparent); }
      .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
      .chip { font-size: 12px; padding: 4px 10px; border-radius: 999px; background: rgba(30,41,59,.8); border: 1px solid rgba(148,163,184,.2); white-space: nowrap; }
      .chip.hot { border-color: #ef4444; color: #fecaca; box-shadow: 0 0 10px rgba(239,68,68,.35); }
      .daily { margin-top: 12px; }
      .sec { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: #94a3b8; margin-bottom: 6px; }
      .sec span:last-child { text-align: right; }
      .dbars { display: grid; gap: 2px; height: 64px; align-items: end; }
      .db { height: 100%; display: flex; align-items: flex-end; min-width: 0; }
      .db i { display: block; width: 100%; height: var(--h); border-radius: 2px 2px 0 0; background: linear-gradient(180deg, var(--c), color-mix(in srgb, var(--c) 35%, transparent));
        animation: grow .9s ease-out both; transform-origin: bottom; }
      .db.fut i { background: none; border: 1px dashed color-mix(in srgb, var(--c) 70%, transparent); border-bottom: none; opacity: .7; }
      .db.today i { box-shadow: 0 0 10px var(--c); animation: grow .9s ease-out both, neonbox 1.6s ease-in-out infinite .9s; }
      details.bd { margin-top: 12px; border-top: 1px solid rgba(148,163,184,.15); padding-top: 8px; }
      summary { cursor: pointer; font-size: 13px; color: #cbd5e1; list-style: none; }
      summary::before { content: "▸ "; color: #fde047; }
      details[open] summary::before { content: "▾ "; }
      .tw { overflow-x: auto; }
      table { color: inherit; width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; font-variant-numeric: tabular-nums; }
      th { color: #94a3b8; font-weight: 600; text-align: right; padding: 4px; }
      td { text-align: right; padding: 4px; border-top: 1px solid rgba(148,163,184,.08); white-space: nowrap; }
      td:first-child { text-align: left; }
      td small { color: #64748b; }
      .f { color: #fde68a; }
      tr.tot td { font-weight: 800; border-top: 1px solid rgba(250,204,21,.35); }
      .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
      .foot { margin-top: 8px; font-size: 11px; color: #64748b; text-align: right; }
      @container (max-width: 400px) {
        ha-card { padding: 12px 10px 10px; }
        .hero { grid-template-columns: minmax(0,1fr) 22px minmax(0,1fr); gap: 4px; }
        .arrow svg { width: 22px; }
        .box { padding: 8px 9px; }
        .sub { font-size: 11px; }
        .lg { font-size: 9.5px; }
        th.f, td.f { display: none; }
      }
      @keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .55; transform: scale(1.35); } }
      @keyframes flow { to { stroke-dashoffset: -20; } }
      @keyframes flick { 0%,92%,100% { opacity: 1; } 94% { opacity: .3; } 96% { opacity: .9; } 98% { opacity: .4; } }
      @keyframes neon { 0%,100% { filter: drop-shadow(0 0 2px var(--c)); } 50% { filter: drop-shadow(0 0 9px var(--c)); } }
      @keyframes neonbox { 0%,100% { box-shadow: 0 0 4px var(--c); } 50% { box-shadow: 0 0 14px var(--c); } }
      @keyframes grow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
      @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; } }
    </style>`;
  }
}

class PowerbillForecastCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({
          entity: "Forecast bill sensor",
          title: "Title",
          show_chips: "Show price chips",
          show_daily: "Show daily energy bars",
          show_breakdown: "Show bill details",
          animate: "Count-up animation",
        })[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = [
      { name: "entity", selector: { entity: { domain: "sensor", integration: "powerbill_forecast" } } },
      { name: "title", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "show_chips", selector: { boolean: {} } },
          { name: "show_daily", selector: { boolean: {} } },
          { name: "show_breakdown", selector: { boolean: {} } },
          { name: "animate", selector: { boolean: {} } },
        ],
      },
    ];
    this._form.data = { show_chips: true, show_daily: true, show_breakdown: true, animate: true, ...this._config };
  }
}

if (!customElements.get("powerbill-forecast-card")) customElements.define("powerbill-forecast-card", PowerbillForecastCard);
if (!customElements.get("powerbill-forecast-card-editor")) customElements.define("powerbill-forecast-card-editor", PowerbillForecastCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "powerbill-forecast-card")) {
  window.customCards.push({
    type: "powerbill-forecast-card",
    name: "Powerbill Forecast",
    description: "Animated tier staircase with live bill and month-end forecast.",
    preview: true,
    documentationURL: "https://github.com/mb26-dev/ha-powerbill-forecast",
  });
}
console.info(`%c ⚡ POWERBILL FORECAST %c ${PBF_VERSION} `, "background:#0b1220;color:#fde047;font-weight:700", "background:#22d3ee;color:#0b1220");
