const CAPITOL_HILL = {
  name: "Washington, DC",
  latitude: 38.8899,
  longitude: -76.9925,
  timezone: "America/New_York"
};

export function buildForecastUrl(location = CAPITOL_HILL) {
  const params = new URLSearchParams({
    latitude: String(location.latitude),
    longitude: String(location.longitude),
    timezone: location.timezone,
    temperature_unit: "fahrenheit",
    wind_speed_unit: "mph",
    precipitation_unit: "inch",
    forecast_days: "1",
    current: [
      "temperature_2m",
      "relative_humidity_2m",
      "apparent_temperature",
      "precipitation",
      "weather_code",
      "wind_speed_10m"
    ].join(","),
    hourly: [
      "temperature_2m",
      "relative_humidity_2m",
      "apparent_temperature",
      "precipitation",
      "weather_code",
      "wind_speed_10m",
      "uv_index"
    ].join(",")
  });

  return `https://api.open-meteo.com/v1/forecast?${params.toString()}`;
}

export async function fetchForecast(fetcher = fetch) {
  const response = await fetcher(buildForecastUrl());
  if (!response.ok) {
    throw new Error(`Weather request failed: ${response.status}`);
  }
  return parseForecast(await response.json());
}

export function parseForecast(payload) {
  const hourly = payload.hourly || {};
  const times = hourly.time || [];
  const now = new Date();
  const currentTime = payload.current?.time ? new Date(payload.current.time) : now;

  const hours = times
    .map((time, index) => ({
      time: new Date(time),
      temperature: hourly.temperature_2m?.[index],
      humidity: hourly.relative_humidity_2m?.[index],
      apparentTemperature: hourly.apparent_temperature?.[index],
      precipitation: hourly.precipitation?.[index],
      weatherCode: hourly.weather_code?.[index],
      windSpeed: hourly.wind_speed_10m?.[index],
      uvIndex: hourly.uv_index?.[index]
    }))
    .filter((hour) => hour.time >= startOfHour(now))
    .filter(hasRequiredWeatherFields);

  const current = {
    time: currentTime,
    temperature: payload.current?.temperature_2m,
    humidity: payload.current?.relative_humidity_2m,
    apparentTemperature: payload.current?.apparent_temperature,
    precipitation: payload.current?.precipitation,
    weatherCode: payload.current?.weather_code,
    windSpeed: payload.current?.wind_speed_10m,
    uvIndex: hours[0]?.uvIndex ?? 0
  };

  return {
    location: CAPITOL_HILL,
    generatedAt: now,
    current: hasRequiredWeatherFields(current) ? current : hours[0],
    hours
  };
}

function hasRequiredWeatherFields(hour) {
  return (
    hour &&
    Number.isFinite(hour.temperature) &&
    Number.isFinite(hour.humidity) &&
    Number.isFinite(hour.windSpeed)
  );
}

function startOfHour(date) {
  const copy = new Date(date);
  copy.setMinutes(0, 0, 0);
  return copy;
}
