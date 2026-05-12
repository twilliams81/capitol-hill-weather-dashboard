import assert from "node:assert/strict";
import test from "node:test";
import { calculateHeatIndex, calculateWindChill, classifyWeather } from "../src/weatherRules.js";

test("31F wind chill is red", () => {
  const result = classifyWeather({
    temperature: 36,
    humidity: 45,
    windSpeed: 10,
    precipitation: 0,
    weatherCode: 0,
    uvIndex: 0
  });

  assert.equal(result.windChill, 29);
  assert.equal(result.status, "red");
});

test("36F wind chill is yellow", () => {
  const result = classifyWeather({
    temperature: 41,
    humidity: 45,
    windSpeed: 8,
    precipitation: 0,
    weatherCode: 0,
    uvIndex: 0
  });

  assert.equal(result.windChill, 36);
  assert.equal(result.status, "yellow");
});

test("55F mild weather is green", () => {
  const result = classifyWeather({
    temperature: 55,
    humidity: 50,
    windSpeed: 5,
    precipitation: 0,
    weatherCode: 1,
    uvIndex: 3
  });

  assert.equal(result.status, "green");
});

test("88F with low humidity is yellow", () => {
  const result = classifyWeather({
    temperature: 88,
    humidity: 25,
    windSpeed: 4,
    precipitation: 0,
    weatherCode: 0,
    uvIndex: 4
  });

  assert.equal(result.status, "yellow");
});

test("96F heat index is red", () => {
  const result = classifyWeather({
    temperature: 92,
    humidity: 44,
    windSpeed: 5,
    precipitation: 0,
    weatherCode: 0,
    uvIndex: 4
  });

  assert.equal(calculateHeatIndex(92, 44), 96);
  assert.equal(result.status, "red");
});

test("82F with high humidity producing 90F heat index is yellow", () => {
  const result = classifyWeather({
    temperature: 82,
    humidity: 85,
    windSpeed: 3,
    precipitation: 0,
    weatherCode: 0,
    uvIndex: 4
  });

  assert.equal(calculateHeatIndex(82, 85), 90);
  assert.equal(result.status, "yellow");
});

test("wind chill formula is not applied above 50F", () => {
  assert.equal(calculateWindChill(55, 15), 55);
});
