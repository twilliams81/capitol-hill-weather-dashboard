import { fetchForecast } from "./weatherApi.js";
import { classifyWeather, pickBestWindows } from "./weatherRules.js";

const app = document.querySelector("#app");

const weatherDescriptions = {
  0: "Clear",
  1: "Mostly clear",
  2: "Partly cloudy",
  3: "Cloudy",
  45: "Fog",
  48: "Freezing fog",
  51: "Light drizzle",
  53: "Drizzle",
  55: "Heavy drizzle",
  61: "Light rain",
  63: "Rain",
  65: "Heavy rain",
  71: "Light snow",
  73: "Snow",
  75: "Heavy snow",
  80: "Light showers",
  81: "Showers",
  82: "Heavy showers",
  95: "Thunderstorm"
};

async function loadDashboard() {
  renderLoading();
  try {
    const forecast = await fetchForecast();
    const current = { ...forecast.current, classification: classifyWeather(forecast.current) };
    const hours = forecast.hours.map((hour) => ({ ...hour, classification: classifyWeather(hour) }));
    renderDashboard({ ...forecast, current, hours });
  } catch (error) {
    renderError(error);
  }
}

function renderLoading() {
  app.innerHTML = `
    <section class="loading-panel">
      <p class="eyebrow">Washington, DC</p>
      <h1>Checking today's outdoor windows...</h1>
      <p>Fetching live hourly weather from Open-Meteo.</p>
    </section>
  `;
}

function renderError(error) {
  app.innerHTML = `
    <section class="error-panel">
      <p class="eyebrow">Weather unavailable</p>
      <h1>Could not load the dashboard.</h1>
      <p>${escapeHtml(error.message)}</p>
      <button class="button" id="refresh">Try again</button>
    </section>
  `;
  document.querySelector("#refresh").addEventListener("click", loadDashboard);
}

function renderDashboard(forecast) {
  const current = forecast.current.classification;
  const hours = forecast.hours.filter((hour) => hour.time.getHours() <= 21);
  const windows = pickBestWindows(hours.map((hour) => ({ ...hour.classification, time: hour.time })));
  const updated = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: forecast.location.timezone
  }).format(forecast.generatedAt);

  app.innerHTML = `
    <header class="topbar">
      <div>
        <p class="eyebrow">${forecast.location.name}</p>
        <h1>Outdoor weather guide</h1>
      </div>
      <button class="button" id="refresh" aria-label="Refresh weather">Refresh</button>
    </header>

    <section class="status-panel ${current.status}">
      <div class="signal" aria-hidden="true">
        <span class="light red ${current.status === "red" ? "active" : ""}"></span>
        <span class="light yellow ${current.status === "yellow" ? "active" : ""}"></span>
        <span class="light green ${current.status === "green" ? "active" : ""}"></span>
      </div>
      <div class="status-copy">
        <p class="eyebrow">Right now</p>
        <h2>${current.label}</h2>
        <p class="tone">${current.tone}</p>
        <p>${current.recommendation}</p>
      </div>
      <dl class="metrics" aria-label="Current weather">
        ${metric("Temp", `${current.tempF}°F`)}
        ${metric("Feels", `${current.feelsLike}°F`)}
        ${metric("Humidity", `${current.humidity}%`)}
        ${metric("Wind", `${current.windMph} mph`)}
        ${metric("UV", `<span>${current.uv.value}</span><small>${current.uv.level}</small>`)}
        ${metric("Mosquito Index", `<span>${current.mosquito.value}/10</span><small>${current.mosquito.level}</small>`)}
      </dl>
    </section>

    <section class="content-grid">
      <article class="panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Today</p>
            <h2>Best outdoor windows</h2>
          </div>
        </div>
        ${renderWindows(windows)}
      </article>

      <article class="panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Decision detail</p>
            <h2>What drove the rating</h2>
          </div>
        </div>
        <ul class="reason-list">
          ${current.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
        </ul>
        <p class="context-line">
          ${weatherDescriptions[current.weatherCode] || "Weather code " + current.weatherCode}.
          ${current.feelsLikeMethod === "heat index" ? "Humidity is included in the heat index." : ""}
          ${current.feelsLikeMethod === "wind chill" ? "Wind is included in the wind chill." : ""}
        </p>
        ${renderUvPanel(current.uv)}
        ${renderMosquitoPanel(current.mosquito)}
      </article>
    </section>

    <section class="panel timeline-panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Now to evening</p>
          <h2>Hourly stoplight</h2>
        </div>
        <p class="updated">Updated ${updated}</p>
      </div>
      <div class="timeline" aria-label="Hourly outdoor guidance">
        ${hours.map(renderHour).join("")}
      </div>
    </section>

    <section class="settings-panel">
      <div>
        <p class="eyebrow">Settings</p>
        <p>Location fixed to Washington, DC. Conservative mode is on for sensitive outdoor conditions.</p>
      </div>
      <p class="disclaimer">Practical planning aid only. Use your judgment and follow relevant health guidance.</p>
    </section>
  `;

  document.querySelector("#refresh").addEventListener("click", loadDashboard);
}

function metric(label, value) {
  return `<div><dt>${label}</dt><dd>${value}</dd></div>`;
}

function renderUvPanel(uv) {
  const levels = ["Low", "Moderate", "High", "Very high", "Extreme"];

  return `
    <div class="uv-panel ${uv.className}" aria-label="UV index detail">
      <div class="uv-header">
        <div>
          <p class="eyebrow">UV index</p>
          <strong>${uv.value} · ${uv.level}</strong>
        </div>
        <span>${uv.guidance}</span>
      </div>
      <div class="uv-scale" aria-hidden="true">
        ${levels
          .map(
            (level) => `
              <span class="${level === uv.level ? "active" : ""}">
                <i></i>
                ${level}
              </span>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderMosquitoPanel(mosquito) {
  const reasons = mosquito.reasons.slice(0, 4).join(", ");

  return `
    <div class="index-panel mosquito-panel ${mosquito.className}" aria-label="Mosquito Index detail">
      <div class="index-header">
        <div>
          <p class="eyebrow">Mosquito Index</p>
          <strong>${mosquito.value}/10 · ${mosquito.level}</strong>
        </div>
        <span>${mosquito.guidance}</span>
      </div>
      <p class="index-detail">Estimated from weather: ${escapeHtml(reasons)}.</p>
    </div>
  `;
}

function renderWindows(windows) {
  if (!windows.length) {
    return `<p class="empty-state">No green windows left today. If you need to go out, use the hourly caution bands and keep it short.</p>`;
  }

  return `
    <div class="window-list">
      ${windows
        .map(
          (window) => `
            <div class="window-item">
              <strong>${formatHour(window.start)}–${formatHour(addHour(window.end))}</strong>
              <span>${window.score} hr · avg feels ${window.averageFeelsLike}°F</span>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderHour(hour) {
  const classification = hour.classification;
  return `
    <div class="hour-card ${classification.status}" title="${classification.reasons.join("; ")}">
      <time>${formatHour(hour.time)}</time>
      <strong>${classification.shortLabel}</strong>
      <span>${classification.feelsLike}°F</span>
      <small>UV ${classification.uv.value} · Mosq ${classification.mosquito.value}</small>
    </div>
  `;
}

function formatHour(date) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    timeZone: "America/New_York"
  }).format(date);
}

function addHour(date) {
  return new Date(date.getTime() + 60 * 60 * 1000);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadDashboard();
