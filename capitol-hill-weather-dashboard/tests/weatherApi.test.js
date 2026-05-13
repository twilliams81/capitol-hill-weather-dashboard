import assert from "node:assert/strict";
import test from "node:test";
import { buildForecastUrl, parseForecast } from "../src/weatherApi.js";

test("forecast URL requests required Open-Meteo fields", () => {
  const url = new URL(buildForecastUrl());

  assert.equal(url.hostname, "api.open-meteo.com");
  assert.equal(url.searchParams.get("temperature_unit"), "fahrenheit");
  assert.equal(url.searchParams.get("wind_speed_unit"), "mph");
  assert.match(url.searchParams.get("current"), /relative_humidity_2m/);
  assert.match(url.searchParams.get("hourly"), /uv_index/);
});

test("parseForecast maps current and hourly weather fields", () => {
  const now = new Date();
  const currentHour = new Date(now);
  currentHour.setMinutes(0, 0, 0);
  const nextHour = new Date(currentHour.getTime() + 60 * 60 * 1000);

  const forecast = parseForecast({
    current: {
      time: currentHour.toISOString(),
      temperature_2m: 72,
      relative_humidity_2m: 56,
      apparent_temperature: 72,
      precipitation: 0,
      weather_code: 1,
      wind_speed_10m: 4
    },
    hourly: {
      time: [currentHour.toISOString(), nextHour.toISOString()],
      temperature_2m: [72, 75],
      relative_humidity_2m: [56, 59],
      apparent_temperature: [72, 76],
      precipitation: [0, 0.01],
      weather_code: [1, 2],
      wind_speed_10m: [4, 6],
      uv_index: [3, 5]
    }
  });

  assert.equal(forecast.location.name, "Washington, DC");
  assert.equal(forecast.current.temperature, 72);
  assert.equal(forecast.current.uvIndex, 3);
  assert.equal(forecast.hours.length, 2);
  assert.equal(forecast.hours[1].humidity, 59);
});
