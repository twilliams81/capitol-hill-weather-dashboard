export const STATUS = {
  green: {
    key: "green",
    label: "Go",
    shortLabel: "best",
    tone: "Good window",
    recommendation:
      "A reasonable window for a short outing. Use shade, dress in light layers, and check his neck, chest, hands, and mood often."
  },
  yellow: {
    key: "yellow",
    label: "Caution",
    shortLabel: "short only",
    tone: "Short, watched outing",
    recommendation:
      "Keep it brief and easy to abandon. Stay in shade, avoid direct sun, and watch for fussiness, flushing, sweating, cold hands, or unusual sleepiness."
  },
  red: {
    key: "red",
    label: "Stay In",
    shortLabel: "avoid",
    tone: "Indoor activity",
    recommendation:
      "Use indoor play unless travel is necessary. The weather is outside the cautious infant range."
  }
};

const THUNDERSTORM_CODES = new Set([95, 96, 99]);
const HEAVY_PRECIP_CODES = new Set([65, 67, 75, 77, 82, 86]);

export function calculateHeatIndex(tempF, humidity) {
  if (tempF < 80) return tempF;

  const T = tempF;
  const R = humidity;
  let hi =
    -42.379 +
    2.04901523 * T +
    10.14333127 * R -
    0.22475541 * T * R -
    0.00683783 * T * T -
    0.05481717 * R * R +
    0.00122874 * T * T * R +
    0.00085282 * T * R * R -
    0.00000199 * T * T * R * R;

  if (R < 13 && T >= 80 && T <= 112) {
    hi -= ((13 - R) / 4) * Math.sqrt((17 - Math.abs(T - 95)) / 17);
  } else if (R > 85 && T >= 80 && T <= 87) {
    hi += ((R - 85) / 10) * ((87 - T) / 5);
  }

  return Math.round(hi);
}

export function calculateWindChill(tempF, windMph) {
  if (tempF > 50 || windMph <= 3) return tempF;

  return Math.round(
    35.74 +
      0.6215 * tempF -
      35.75 * Math.pow(windMph, 0.16) +
      0.4275 * tempF * Math.pow(windMph, 0.16)
  );
}

export function getFeelsLike(tempF, humidity, windMph) {
  const heatIndex = calculateHeatIndex(tempF, humidity);
  const windChill = calculateWindChill(tempF, windMph);

  if (tempF >= 80) return { value: heatIndex, method: "heat index", heatIndex, windChill };
  if (tempF <= 50 && windMph > 3) return { value: windChill, method: "wind chill", heatIndex, windChill };
  return { value: Math.round(tempF), method: "air temperature", heatIndex, windChill };
}

export function classifyWeather(hour) {
  const tempF = Math.round(hour.temperature);
  const humidity = Math.round(hour.humidity);
  const windMph = Math.round(hour.windSpeed);
  const uvIndex = Number.isFinite(hour.uvIndex) ? hour.uvIndex : 0;
  const precipitation = Number.isFinite(hour.precipitation) ? hour.precipitation : 0;
  const weatherCode = Number.isFinite(hour.weatherCode) ? hour.weatherCode : 0;
  const feelsLike = getFeelsLike(tempF, humidity, windMph);
  const reasons = [];
  let status = "green";

  if (feelsLike.value < 32) {
    status = "red";
    reasons.push(`${feelsLike.method} is below 32°F`);
  }

  if (feelsLike.heatIndex > 95) {
    status = "red";
    reasons.push(`heat index is ${feelsLike.heatIndex}°F`);
  }

  if (THUNDERSTORM_CODES.has(weatherCode) || HEAVY_PRECIP_CODES.has(weatherCode) || precipitation >= 0.2) {
    status = "red";
    reasons.push("heavy precipitation or storm risk");
  }

  if (uvIndex >= 9 && tempF >= 80) {
    status = "red";
    reasons.push(`UV index is ${Math.round(uvIndex)} during warm weather`);
  }

  if (status !== "red") {
    if (feelsLike.value < 40 && feelsLike.value >= 32) {
      status = "yellow";
      reasons.push(`${feelsLike.method} is below 40°F`);
    }

    if (feelsLike.heatIndex >= 85 || tempF >= 85) {
      status = "yellow";
      reasons.push(`heat caution range: ${Math.max(feelsLike.heatIndex, tempF)}°F`);
    }

    if (tempF >= 80 && feelsLike.heatIndex - tempF >= 6) {
      status = "yellow";
      reasons.push(`humidity adds ${feelsLike.heatIndex - tempF}°F`);
    }

    if (uvIndex >= 6) {
      status = "yellow";
      reasons.push(`UV index is ${Math.round(uvIndex)}`);
    }

    if (precipitation >= 0.05) {
      status = "yellow";
      reasons.push("rain likely");
    }
  }

  if (reasons.length === 0) {
    reasons.push("temperature, humidity, wind, and precipitation are in the cautious infant range");
  }

  return {
    status,
    ...STATUS[status],
    tempF,
    humidity,
    windMph,
    uvIndex,
    precipitation,
    weatherCode,
    feelsLike: feelsLike.value,
    feelsLikeMethod: feelsLike.method,
    heatIndex: feelsLike.heatIndex,
    windChill: feelsLike.windChill,
    reasons
  };
}

export function pickBestWindows(classifiedHours, maxWindows = 3) {
  const windows = [];
  let current = null;

  classifiedHours.forEach((hour) => {
    if (hour.status !== "green") {
      if (current) windows.push(current);
      current = null;
      return;
    }

    if (!current) {
      current = { start: hour.time, end: hour.time, hours: [hour] };
    } else {
      current.end = hour.time;
      current.hours.push(hour);
    }
  });

  if (current) windows.push(current);

  return windows
    .map((window) => ({
      ...window,
      score: window.hours.length,
      averageFeelsLike: Math.round(
        window.hours.reduce((sum, hour) => sum + hour.feelsLike, 0) / window.hours.length
      )
    }))
    .sort((a, b) => b.score - a.score || Math.abs(a.averageFeelsLike - 68) - Math.abs(b.averageFeelsLike - 68))
    .slice(0, maxWindows)
    .sort((a, b) => a.start - b.start);
}
