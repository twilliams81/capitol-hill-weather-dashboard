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
  const rain = summarizeRain(hours);
  const clothing = getClothingGuidance(current, rain);
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
        ${metric("Rain", `<span>${rain.summary}</span><small>${rain.metricDetail}</small>`)}
        ${metric("Clothing", `<span>${clothing.summary}</span><small>${clothing.metricDetail}</small>`)}
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
        ${renderRainPanel(rain)}
        ${renderClothingPanel(clothing)}
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

function summarizeRain(hours) {
  const rainyHours = hours.filter((hour) => hour.classification.precipitation >= 0.01);
  const nowHour = hours[0]?.time;

  if (!rainyHours.length) {
    return {
      summary: "None",
      metricDetail: "through evening",
      level: "None",
      className: "rain-none",
      headline: "No rain expected through evening.",
      detail: "No measurable hourly rain is forecast in the current window."
    };
  }

  const peak = rainyHours.reduce((max, hour) =>
    hour.classification.precipitation > max.classification.precipitation ? hour : max
  );
  const first = rainyHours[0];
  const last = rainyHours[rainyHours.length - 1];
  const nextDry = hours.find((hour) => hour.time > last.time && hour.classification.precipitation < 0.01);
  const start = formatHour(first.time);
  const peakTime = formatHour(peak.time);
  const end = nextDry ? formatHour(nextDry.time) : `after ${formatHour(addHour(last.time))}`;
  const trend = getRainTrend(rainyHours);
  const trendDetail = getRainTrendDetail(rainyHours, peakTime);
  const level = describeRainIntensity(peak.classification.precipitation);
  const isCurrent = nowHour && first.time.getTime() === nowHour.getTime();

  return {
    summary: isCurrent ? `${level.label} now` : `${level.label} at ${start}`,
    metricDetail: `${trendDetail}; ends ${end}`,
    level: level.label,
    className: level.className,
    headline: isCurrent
      ? `${level.label} rain now.`
      : `${level.label} rain expected ${start === peakTime ? `at ${start}` : `from ${start}`}.`,
    detail: `Rain ${trendDetail}; expected to end ${end}. Peak rate ${formatRainAmount(peak.classification.precipitation)}/hr.`
  };
}

function describeRainIntensity(amount) {
  if (amount >= 0.2) return { label: "Heavy", className: "rain-heavy" };
  if (amount >= 0.05) return { label: "Light", className: "rain-light" };
  return { label: "Drizzle", className: "rain-drizzle" };
}

function getRainTrend(rainyHours) {
  if (rainyHours.length < 2) return "brief";

  const first = rainyHours[0].classification.precipitation;
  const last = rainyHours[rainyHours.length - 1].classification.precipitation;
  const peak = Math.max(...rainyHours.map((hour) => hour.classification.precipitation));

  if (last >= first + 0.03) return "gets heavier";
  if (first >= last + 0.03) return "gets lighter";
  if (peak >= first + 0.03 && peak >= last + 0.03) return "peaks mid-window";
  return "stays fairly steady";
}

function getRainTrendDetail(rainyHours, peakTime) {
  const trend = getRainTrend(rainyHours);

  if (trend === "gets heavier") return `heavier by ${peakTime}`;
  if (trend === "gets lighter") return `lighter by ${peakTime}`;
  if (trend === "peaks mid-window") return `peaks ${peakTime}`;
  return trend;
}

function formatRainAmount(amount) {
  if (amount < 0.01) return "0 in";
  return `${amount.toFixed(2)} in`;
}

function getClothingGuidance(current, rain) {
  const feels = current.feelsLike;
  const items = [];
  let summary = "Light layer";
  let metricDetail = "comfortable";
  let className = "mild";
  let headline = "Light layer should be enough.";

  if (feels < 32) {
    summary = "Bundle up";
    metricDetail = "indoor best";
    className = "cold";
    headline = "Indoor activity is the safer default.";
    items.push("Warm base layer, insulating layer, hat, mittens, socks, and windproof outer layer.");
  } else if (feels < 40) {
    summary = "Warm layers";
    metricDetail = "hat + mittens";
    className = "cold";
    headline = "Use warm, removable layers.";
    items.push("Warm base layer, coat or bunting, hat, mittens, warm socks, and a wind-blocking outer layer.");
  } else if (feels < 55) {
    summary = "Coat layer";
    metricDetail = "cover hands";
    className = "cool";
    headline = "Use a coat or fleece layer.";
    items.push("Long sleeves, pants, socks, and a coat or fleece; add a hat if it feels windy.");
  } else if (feels < 70) {
    summary = "Light layer";
    metricDetail = "bring backup";
    className = "mild";
    headline = "Use a light removable layer.";
    items.push("Long sleeves or a light jacket over comfortable clothes; bring a backup layer.");
  } else if (feels < 85) {
    summary = "Light clothes";
    metricDetail = "shade + hat";
    className = "warm";
    headline = "Use light, breathable clothing.";
    items.push("Lightweight, breathable clothes; use shade and a brimmed hat when the sun is strong.");
  } else if (feels <= 95) {
    summary = "Keep cool";
    metricDetail = "loose + light";
    className = "hot";
    headline = "Dress for heat and keep the outing short.";
    items.push("Loose, lightweight, light-colored clothing; avoid extra blankets and direct sun.");
  } else {
    summary = "Stay cool";
    metricDetail = "indoor best";
    className = "hot";
    headline = "Indoor activity is the safer default in this heat.";
    items.push("If travel is necessary, use loose, lightweight, light-colored clothing and shade.");
  }

  if (current.uv.value >= 6) {
    items.push("For high UV, use shade plus a brimmed hat and lightweight skin-covering clothing.");
  }

  if (current.windMph >= 12 && feels < 65) {
    items.push("Wind is noticeable, so favor an outer layer that blocks wind.");
  }

  if (rain.className !== "rain-none") {
    items.push(`Pack a rain cover or waterproof layer if out near the rain window (${rain.summary}).`);
  }

  if (current.mosquito.value >= 3) {
    items.push("Long sleeves and pants can also reduce mosquito bites in sheltered areas.");
  }

  return {
    summary,
    metricDetail,
    className,
    headline,
    items
  };
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

function renderRainPanel(rain) {
  return `
    <div class="index-panel rain-panel ${rain.className}" aria-label="Rain detail">
      <p class="eyebrow">Rain</p>
      <strong>${escapeHtml(rain.headline)}</strong>
      <p class="index-detail">${escapeHtml(rain.detail)}</p>
    </div>
  `;
}

function renderClothingPanel(clothing) {
  return `
    <div class="index-panel clothing-panel ${clothing.className}" aria-label="Clothing guidance">
      <p class="eyebrow">Clothing</p>
      <strong>${escapeHtml(clothing.headline)}</strong>
      <ul class="compact-list">
        ${clothing.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
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
      ${classification.precipitation >= 0.01 ? `<small>Rain ${formatRainAmount(classification.precipitation)}</small>` : ""}
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
