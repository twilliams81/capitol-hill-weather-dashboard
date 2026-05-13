import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateHeatIndex,
  calculateMosquitoIndex,
  calculateWindChill,
  classifyWeather,
  describeUvIndex
} from "../src/weatherRules.js";

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

test("UV index is grouped into clear risk bands", () => {
  assert.equal(describeUvIndex(2).level, "Low");
  assert.equal(describeUvIndex(5).level, "Moderate");
  assert.equal(describeUvIndex(7).level, "High");
  assert.equal(describeUvIndex(9).level, "Very high");
  assert.equal(describeUvIndex(11).level, "Extreme");
});

test("mosquito index rises with warm humid calm evening weather", () => {
  const result = calculateMosquitoIndex({
    time: new Date("2026-07-01T19:00:00-04:00"),
    temperature: 78,
    humidity: 76,
    windSpeed: 2,
    precipitation: 0.06
  });

  assert.equal(result.value, 10);
  assert.equal(result.level, "Very high");
});

test("mosquito index stays low in dry windy weather", () => {
  const result = calculateMosquitoIndex({
    time: new Date("2026-05-01T14:00:00-04:00"),
    temperature: 72,
    humidity: 34,
    windSpeed: 14,
    precipitation: 0
  });

  assert.equal(result.value, 2);
  assert.equal(result.level, "Low");
});
