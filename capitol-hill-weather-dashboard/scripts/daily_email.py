#!/usr/bin/env python3
import argparse
import html
import json
import math
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

LOCATION = {
    "name": "Washington, DC",
    "latitude": 38.8899,
    "longitude": -76.9925,
    "timezone": "America/New_York",
}

STATUS = {
    "green": {
        "label": "Go",
        "tone": "Good window",
        "recommendation": (
            "A reasonable window for a short outing. Use shade, dress in light "
            "layers, and keep an eye on comfort."
        ),
    },
    "yellow": {
        "label": "Caution",
        "tone": "Short, watched outing",
        "recommendation": (
            "Keep it brief and easy to abandon. Stay in shade, avoid direct sun, "
            "and watch for fussiness, flushing, sweating, cold hands, or unusual "
            "sleepiness."
        ),
    },
    "red": {
        "label": "Stay In",
        "tone": "Indoor activity",
        "recommendation": (
            "Use indoor play unless travel is necessary. The weather is outside "
            "the cautious range."
        ),
    },
}

THUNDERSTORM_CODES = {95, 96, 99}
HEAVY_PRECIP_CODES = {65, 67, 75, 77, 82, 86}

WEATHER_DESCRIPTIONS = {
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
    95: "Thunderstorm",
}


def forecast_url():
    params = {
        "latitude": LOCATION["latitude"],
        "longitude": LOCATION["longitude"],
        "timezone": LOCATION["timezone"],
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": 1,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "uv_index",
            ]
        ),
    }
    return f"https://api.open-meteo.com/v1/forecast?{urlencode(params)}"


def calculate_heat_index(temp_f, humidity):
    if temp_f < 80:
        return temp_f

    t = temp_f
    r = humidity
    heat_index = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )

    if r < 13 and 80 <= t <= 112:
        heat_index -= ((13 - r) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
    elif r > 85 and 80 <= t <= 87:
        heat_index += ((r - 85) / 10) * ((87 - t) / 5)

    return round(heat_index)


def calculate_wind_chill(temp_f, wind_mph):
    if temp_f > 50 or wind_mph <= 3:
        return temp_f

    return round(
        35.74
        + 0.6215 * temp_f
        - 35.75 * (wind_mph**0.16)
        + 0.4275 * temp_f * (wind_mph**0.16)
    )


def feels_like(temp_f, humidity, wind_mph):
    heat_index = calculate_heat_index(temp_f, humidity)
    wind_chill = calculate_wind_chill(temp_f, wind_mph)
    if temp_f >= 80:
        return heat_index, "heat index", heat_index, wind_chill
    if temp_f <= 50 and wind_mph > 3:
        return wind_chill, "wind chill", heat_index, wind_chill
    return round(temp_f), "air temperature", heat_index, wind_chill


def describe_uv_index(uv_index):
    value = round(uv_index if isinstance(uv_index, (int, float)) else 0)
    if value >= 11:
        return {
            "value": value,
            "level": "Extreme",
            "class_name": "extreme",
            "guidance": "Avoid direct sun.",
        }
    if value >= 8:
        return {
            "value": value,
            "level": "Very high",
            "class_name": "very-high",
            "guidance": "Use shade and shorten exposure.",
        }
    if value >= 6:
        return {
            "value": value,
            "level": "High",
            "class_name": "high",
            "guidance": "Shade matters.",
        }
    if value >= 3:
        return {
            "value": value,
            "level": "Moderate",
            "class_name": "moderate",
            "guidance": "Some sun caution.",
        }
    return {
        "value": value,
        "level": "Low",
        "class_name": "low",
        "guidance": "UV is a minor factor.",
    }


def calculate_mosquito_index(hour):
    temp_f = hour.get("temperature") or 0
    humidity = hour.get("humidity") or 0
    wind_mph = hour.get("wind_speed") or 0
    precipitation = hour.get("precipitation") or 0
    hour_time = hour.get("time")
    hour_of_day = hour_time.hour if isinstance(hour_time, datetime) else None
    evening = hour_of_day is not None and (hour_of_day >= 18 or hour_of_day <= 7)
    reasons = []
    score = 0

    if 70 <= temp_f <= 90:
        score += 3
        reasons.append("warm")
    elif 60 <= temp_f < 70:
        score += 1
        reasons.append("mild")
    elif temp_f > 90:
        score += 1
        reasons.append("hot")
    else:
        reasons.append("cool")

    if humidity >= 70:
        score += 3
        reasons.append("humid")
    elif humidity >= 55:
        score += 2
        reasons.append("some humidity")
    elif humidity >= 40:
        score += 1
        reasons.append("limited humidity")
    else:
        reasons.append("dry")

    if wind_mph <= 4:
        score += 2
        reasons.append("calm wind")
    elif wind_mph <= 9:
        score += 1
        reasons.append("light wind")
    else:
        score -= 1
        reasons.append("wind helps")

    if precipitation >= 0.05:
        score += 1
        reasons.append("rain")
    if evening:
        score += 1
        reasons.append("evening timing")

    value = max(0, min(10, round(score)))
    level = "Low"
    class_name = "low"
    guidance = "Mosquitoes are unlikely to shape the outing."

    if value >= 8:
        level = "Very high"
        class_name = "very-high"
        guidance = "Expect bites in still or shaded areas."
    elif value >= 6:
        level = "High"
        class_name = "high"
        guidance = "Consider lighter-colored clothing and avoid still, shaded spots."
    elif value >= 3:
        level = "Moderate"
        class_name = "moderate"
        guidance = "Possible in sheltered or damp areas."

    return {
        "value": value,
        "level": level,
        "class_name": class_name,
        "guidance": guidance,
        "reasons": reasons,
    }


def classify(hour):
    temp_f = round(hour["temperature"])
    humidity = round(hour["humidity"])
    wind_mph = round(hour["wind_speed"])
    uv_index = hour.get("uv_index") or 0
    precipitation = hour.get("precipitation") or 0
    weather_code = int(hour.get("weather_code") or 0)
    feels, method, heat_index, wind_chill = feels_like(temp_f, humidity, wind_mph)
    uv = describe_uv_index(uv_index)
    mosquito = calculate_mosquito_index(hour)
    status = "green"
    reasons = []

    if feels < 32:
        status = "red"
        reasons.append(f"{method} is below 32F")
    if heat_index > 95:
        status = "red"
        reasons.append(f"heat index is {heat_index}F")
    if (
        weather_code in THUNDERSTORM_CODES
        or weather_code in HEAVY_PRECIP_CODES
        or precipitation >= 0.2
    ):
        status = "red"
        reasons.append("heavy precipitation or storm risk")
    if uv_index >= 9 and temp_f >= 80:
        status = "red"
        reasons.append(f"UV index is {uv['value']} ({uv['level']}) during warm weather")

    if status != "red":
        if 32 <= feels < 40:
            status = "yellow"
            reasons.append(f"{method} is below 40F")
        if heat_index >= 85 or temp_f >= 85:
            status = "yellow"
            reasons.append(f"heat caution range: {max(heat_index, temp_f)}F")
        if temp_f >= 80 and heat_index - temp_f >= 6:
            status = "yellow"
            reasons.append(f"humidity adds {heat_index - temp_f}F")
        if uv_index >= 6:
            status = "yellow"
            reasons.append(f"UV index is {uv['value']} ({uv['level']})")
        if precipitation >= 0.05:
            status = "yellow"
            reasons.append("rain likely")

    if not reasons:
        reasons.append(
            "temperature, humidity, wind, and precipitation are in the cautious outdoor range"
        )

    return {
        **STATUS[status],
        "status": status,
        "temp_f": temp_f,
        "humidity": humidity,
        "wind_mph": wind_mph,
        "uv_index": uv_index,
        "uv": uv,
        "mosquito": mosquito,
        "precipitation": precipitation,
        "weather_code": weather_code,
        "feels_like": feels,
        "feels_like_method": method,
        "reasons": reasons,
    }


def fetch_forecast():
    with urlopen(forecast_url(), timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    now = datetime.now(ZoneInfo(LOCATION["timezone"]))
    hourly = payload["hourly"]
    hours = []
    for index, value in enumerate(hourly["time"]):
        hour_time = datetime.fromisoformat(value)
        if hour_time.hour < now.hour or hour_time.hour > 21:
            continue
        hour = {
            "time": hour_time,
            "temperature": hourly["temperature_2m"][index],
            "humidity": hourly["relative_humidity_2m"][index],
            "apparent_temperature": hourly["apparent_temperature"][index],
            "precipitation": hourly["precipitation"][index],
            "weather_code": hourly["weather_code"][index],
            "wind_speed": hourly["wind_speed_10m"][index],
            "uv_index": hourly["uv_index"][index],
        }
        hour["classification"] = classify(hour)
        hours.append(hour)

    current = {
        "time": datetime.fromisoformat(payload["current"]["time"]),
        "temperature": payload["current"]["temperature_2m"],
        "humidity": payload["current"]["relative_humidity_2m"],
        "apparent_temperature": payload["current"]["apparent_temperature"],
        "precipitation": payload["current"]["precipitation"],
        "weather_code": payload["current"]["weather_code"],
        "wind_speed": payload["current"]["wind_speed_10m"],
        "uv_index": hours[0]["uv_index"] if hours else 0,
    }
    current["classification"] = classify(current)
    return current, hours


def best_windows(hours, max_windows=3):
    windows = []
    current = []
    for hour in hours:
        if hour["classification"]["status"] == "green":
            current.append(hour)
        else:
            if current:
                windows.append(current)
            current = []
    if current:
        windows.append(current)

    scored = []
    for window in windows:
        average = round(
            sum(hour["classification"]["feels_like"] for hour in window) / len(window)
        )
        scored.append(
            {
                "start": window[0]["time"],
                "end": window[-1]["time"] + timedelta(hours=1),
                "score": len(window),
                "average_feels": average,
            }
        )

    return sorted(
        sorted(
            scored,
            key=lambda item: (-item["score"], abs(item["average_feels"] - 68)),
        )[:max_windows],
        key=lambda item: item["start"],
    )


def best_windows_text(hours):
    windows = best_windows(hours)
    if not windows:
        return "No green windows left today."
    return "; ".join(
        f"{window['start'].strftime('%-I %p')}-{window['end'].strftime('%-I %p')}, "
        f"{window['score']} hr, avg feels {window['average_feels']}F"
        for window in windows
    )


def summarize_rain(hours):
    rainy_hours = [
        hour for hour in hours if hour["classification"]["precipitation"] >= 0.01
    ]
    now_hour = hours[0]["time"] if hours else None

    if not rainy_hours:
        return {
            "summary": "None",
            "metric_detail": "through evening",
            "level": "None",
            "class_name": "rain-none",
            "headline": "No rain expected through evening.",
            "detail": "No measurable hourly rain is forecast in the current window.",
        }

    peak = max(rainy_hours, key=lambda hour: hour["classification"]["precipitation"])
    first = rainy_hours[0]
    last = rainy_hours[-1]
    next_dry = next(
        (
            hour
            for hour in hours
            if hour["time"] > last["time"]
            and hour["classification"]["precipitation"] < 0.01
        ),
        None,
    )
    start = first["time"].strftime("%-I %p")
    peak_time = peak["time"].strftime("%-I %p")
    end = (
        next_dry["time"].strftime("%-I %p")
        if next_dry
        else f"after {(last['time'] + timedelta(hours=1)).strftime('%-I %p')}"
    )
    trend_detail = get_rain_trend_detail(rainy_hours, peak_time)
    level = describe_rain_intensity(peak["classification"]["precipitation"])
    is_current = now_hour and first["time"] == now_hour

    return {
        "summary": f"{level['label']} now" if is_current else f"{level['label']} at {start}",
        "metric_detail": f"{trend_detail}; ends {end}",
        "level": level["label"],
        "class_name": level["class_name"],
        "headline": (
            f"{level['label']} rain now."
            if is_current
            else f"{level['label']} rain expected "
            f"{'at ' + start if start == peak_time else 'from ' + start}."
        ),
        "detail": (
            f"Rain {trend_detail}; expected to end {end}. "
            f"Peak rate {format_rain_amount(peak['classification']['precipitation'])}/hr."
        ),
    }


def describe_rain_intensity(amount):
    if amount >= 0.2:
        return {"label": "Heavy", "class_name": "rain-heavy"}
    if amount >= 0.05:
        return {"label": "Light", "class_name": "rain-light"}
    return {"label": "Drizzle", "class_name": "rain-drizzle"}


def get_rain_trend(rainy_hours):
    if len(rainy_hours) < 2:
        return "brief"
    first = rainy_hours[0]["classification"]["precipitation"]
    last = rainy_hours[-1]["classification"]["precipitation"]
    peak = max(hour["classification"]["precipitation"] for hour in rainy_hours)
    if last >= first + 0.03:
        return "gets heavier"
    if first >= last + 0.03:
        return "gets lighter"
    if peak >= first + 0.03 and peak >= last + 0.03:
        return "peaks mid-window"
    return "stays fairly steady"


def get_rain_trend_detail(rainy_hours, peak_time):
    trend = get_rain_trend(rainy_hours)
    if trend == "gets heavier":
        return f"heavier by {peak_time}"
    if trend == "gets lighter":
        return f"lighter by {peak_time}"
    if trend == "peaks mid-window":
        return f"peaks {peak_time}"
    return trend


def format_rain_amount(amount):
    if amount < 0.01:
        return "0 in"
    return f"{amount:.2f} in"


def get_clothing_guidance(current, rain):
    feels = current["feels_like"]
    items = []
    summary = "Light layer"
    metric_detail = "comfortable"
    class_name = "mild"
    headline = "Light layer should be enough."

    if feels < 32:
        summary = "Bundle up"
        metric_detail = "indoor best"
        class_name = "cold"
        headline = "Indoor activity is the safer default."
        items.append(
            "Warm base layer, insulating layer, hat, mittens, socks, and windproof outer layer."
        )
    elif feels < 40:
        summary = "Warm layers"
        metric_detail = "hat + mittens"
        class_name = "cold"
        headline = "Use warm, removable layers."
        items.append(
            "Warm base layer, coat or bunting, hat, mittens, warm socks, and a wind-blocking outer layer."
        )
    elif feels < 55:
        summary = "Coat layer"
        metric_detail = "cover hands"
        class_name = "cool"
        headline = "Use a coat or fleece layer."
        items.append(
            "Long sleeves, pants, socks, and a coat or fleece; add a hat if it feels windy."
        )
    elif feels < 70:
        summary = "Light layer"
        metric_detail = "bring backup"
        class_name = "mild"
        headline = "Use a light removable layer."
        items.append(
            "Long sleeves or a light jacket over comfortable clothes; bring a backup layer."
        )
    elif feels < 85:
        summary = "Light clothes"
        metric_detail = "shade + hat"
        class_name = "warm"
        headline = "Use light, breathable clothing."
        items.append(
            "Lightweight, breathable clothes; use shade and a brimmed hat when the sun is strong."
        )
    elif feels <= 95:
        summary = "Keep cool"
        metric_detail = "loose + light"
        class_name = "hot"
        headline = "Dress for heat and keep the outing short."
        items.append(
            "Loose, lightweight, light-colored clothing; avoid extra blankets and direct sun."
        )
    else:
        summary = "Stay cool"
        metric_detail = "indoor best"
        class_name = "hot"
        headline = "Indoor activity is the safer default in this heat."
        items.append(
            "If travel is necessary, use loose, lightweight, light-colored clothing and shade."
        )

    if current["uv"]["value"] >= 6:
        items.append(
            "For high UV, use shade plus a brimmed hat and lightweight skin-covering clothing."
        )
    if current["wind_mph"] >= 12 and feels < 65:
        items.append("Wind is noticeable, so favor an outer layer that blocks wind.")
    if rain["class_name"] != "rain-none":
        items.append(
            f"Pack a rain cover or waterproof layer if out near the rain window ({rain['summary']})."
        )
    if current["mosquito"]["value"] >= 3:
        items.append("Long sleeves and pants can also reduce mosquito bites in sheltered areas.")

    return {
        "summary": summary,
        "metric_detail": metric_detail,
        "class_name": class_name,
        "headline": headline,
        "items": items,
    }


def build_message(current, hours, dashboard_url):
    c = current["classification"]
    rain = summarize_rain(hours)
    clothing = get_clothing_guidance(c, rain)
    windows = best_windows(hours)
    local_time = datetime.now(ZoneInfo(LOCATION["timezone"])).strftime(
        "%A, %B %-d at %-I:%M %p"
    )
    reason_lines = "\n".join(f"- {reason}" for reason in c["reasons"])
    hourly_lines = [
        f"{hour['time'].strftime('%-I %p')}: {hour['classification']['label']} "
        f"({hour['classification']['feels_like']}F feels-like, "
        f"UV {hour['classification']['uv']['value']}, "
        f"Mosq {hour['classification']['mosquito']['value']}"
        f"{', rain ' + format_rain_amount(hour['classification']['precipitation']) if hour['classification']['precipitation'] >= 0.01 else ''})"
        for hour in hours[:10]
    ]
    best_text = best_windows_text(hours)
    clothing_lines = "\n".join(f"- {item}" for item in clothing["items"])
    weather_text = WEATHER_DESCRIPTIONS.get(c["weather_code"], f"Weather code {c['weather_code']}")

    subject = f"DC outdoor weather: {c['label']} ({c['feels_like']}F feels-like)"
    text = f"""DC outdoor weather guide
{local_time}

Right now: {c['label']} - {c['tone']}
Temp: {c['temp_f']}F
Feels like: {c['feels_like']}F ({c['feels_like_method']})
Humidity: {c['humidity']}%
Wind: {c['wind_mph']} mph
UV: {c['uv']['value']} ({c['uv']['level']})
Mosquito Index: {c['mosquito']['value']}/10 ({c['mosquito']['level']})
Rain: {rain['summary']} - {rain['metric_detail']}
Clothing: {clothing['summary']} - {clothing['metric_detail']}

Recommendation:
{c['recommendation']}

Why:
{reason_lines}

Best window:
{best_text}

UV:
{c['uv']['value']} ({c['uv']['level']}) - {c['uv']['guidance']}

Mosquito Index:
{c['mosquito']['value']}/10 ({c['mosquito']['level']}) - {c['mosquito']['guidance']}
Estimated from weather: {", ".join(c['mosquito']['reasons'][:4])}.

Rain:
{rain['headline']}
{rain['detail']}

Clothing:
{clothing['headline']}
{clothing_lines}

Hourly:
{chr(10).join(hourly_lines)}
"""

    if dashboard_url:
        text += f"\nDashboard: {dashboard_url}\n"

    status_colors = {
        "green": ("#177245", "#e6f4ec"),
        "yellow": ("#9a6700", "#fff3ca"),
        "red": ("#a32626", "#fde5e2"),
    }
    status_color, status_bg = status_colors[c["status"]]

    def h(value):
        return html.escape(str(value))

    def metric_cell(label, value, detail=""):
        return (
            '<td style="width:50%;vertical-align:top;padding:5px;">'
            '<div style="border:1px solid #d7ddd2;border-radius:8px;'
            'padding:12px;background:#ffffff;">'
            f'<div style="color:#5f665d;font-size:12px;font-weight:700;">{h(label)}</div>'
            f'<div style="font-size:22px;font-weight:800;color:#202124;">{h(value)}</div>'
            f'<div style="color:#5f665d;font-size:13px;font-weight:700;">{h(detail)}</div>'
            "</div></td>"
        )

    def detail_card(title, headline, body, bg="#ffffff", border="#d7ddd2"):
        return (
            f'<div style="border:1px solid {border};border-radius:8px;'
            f'padding:14px;background:{bg};margin:12px 0;">'
            '<div style="color:#2f5b7c;font-size:11px;font-weight:800;'
            'letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">'
            f"{h(title)}</div>"
            f'<div style="font-size:18px;font-weight:800;color:#202124;line-height:1.25;">{h(headline)}</div>'
            f'<div style="color:#5f665d;font-size:14px;font-weight:600;line-height:1.4;margin-top:8px;">{body}</div>'
            "</div>"
        )

    metrics = [
        ("Temp", f"{c['temp_f']}F", ""),
        ("Feels", f"{c['feels_like']}F", c["feels_like_method"]),
        ("Humidity", f"{c['humidity']}%", ""),
        ("Wind", f"{c['wind_mph']} mph", ""),
        ("UV", c["uv"]["value"], c["uv"]["level"]),
        (
            "Mosquito Index",
            f"{c['mosquito']['value']}/10",
            c["mosquito"]["level"],
        ),
        ("Rain", rain["summary"], rain["metric_detail"]),
        ("Clothing", clothing["summary"], clothing["metric_detail"]),
    ]
    metric_html = "".join(
        "<tr>"
        + "".join(metric_cell(label, value, detail) for label, value, detail in metrics[index : index + 2])
        + ("<td></td>" if len(metrics[index : index + 2]) == 1 else "")
        + "</tr>"
        for index in range(0, len(metrics), 2)
    )

    window_html = (
        '<p style="margin:0;color:#5f665d;font-weight:700;">No green windows left today.</p>'
        if not windows
        else "".join(
            '<div style="border-top:1px solid #d7ddd2;padding:10px 0;">'
            f'<strong>{h(window["start"].strftime("%-I %p"))}-{h(window["end"].strftime("%-I %p"))}</strong>'
            f'<span style="float:right;color:#5f665d;">{window["score"]} hr, avg feels {window["average_feels"]}F</span>'
            '<div style="clear:both;"></div>'
            "</div>"
            for window in windows
        )
    )

    hourly_html = "".join(
        '<tr>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;font-weight:800;">{h(hour["time"].strftime("%-I %p"))}</td>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;">{h(hour["classification"]["label"])}</td>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;">{hour["classification"]["feels_like"]}F</td>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;">UV {hour["classification"]["uv"]["value"]}</td>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;">Mosq {hour["classification"]["mosquito"]["value"]}</td>'
        f'<td style="padding:8px;border-bottom:1px solid #d7ddd2;">{h(format_rain_amount(hour["classification"]["precipitation"]) if hour["classification"]["precipitation"] >= 0.01 else "-")}</td>'
        "</tr>"
        for hour in hours[:10]
    )

    html_body = f"""
    <div style="margin:0;padding:0;background:#fbfbf7;color:#202124;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
      <div style="max-width:760px;margin:0 auto;padding:24px;">
        <div style="color:#2f5b7c;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;">{h(LOCATION['name'])}</div>
        <h1 style="margin:4px 0 16px;font-size:30px;line-height:1.1;">DC outdoor weather guide</h1>
        <div style="border:1px solid #d7ddd2;border-left:8px solid {status_color};border-radius:8px;background:{status_bg};padding:20px;margin-bottom:16px;">
          <div style="color:#2f5b7c;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;">Right now</div>
          <div style="font-size:52px;line-height:1;font-weight:850;margin:6px 0;color:#202124;">{h(c['label'])}</div>
          <div style="font-weight:800;margin-bottom:8px;">{h(c['tone'])}</div>
          <div style="font-size:15px;line-height:1.35;max-width:620px;">{h(c['recommendation'])}</div>
          <table style="width:100%;border-collapse:separate;border-spacing:0;margin-top:16px;">
            {metric_html}
          </table>
        </div>

        <div style="border:1px solid #d7ddd2;border-radius:8px;background:#ffffff;padding:16px;margin-bottom:16px;">
          <div style="color:#2f5b7c;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;">Today</div>
          <h2 style="margin:4px 0 12px;font-size:20px;">Best outdoor windows</h2>
          {window_html}
        </div>

        <div style="border:1px solid #d7ddd2;border-radius:8px;background:#ffffff;padding:16px;margin-bottom:16px;">
          <div style="color:#2f5b7c;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;">Decision detail</div>
          <h2 style="margin:4px 0 12px;font-size:20px;">What drove the rating</h2>
          <ul style="margin:0 0 12px 18px;padding:0;">{''.join(f'<li style="margin-bottom:6px;">{h(reason)}</li>' for reason in c['reasons'])}</ul>
          <p style="margin:0;color:#5f665d;">{h(weather_text)}. {h('Humidity is included in the heat index.' if c['feels_like_method'] == 'heat index' else '')}{h('Wind is included in the wind chill.' if c['feels_like_method'] == 'wind chill' else '')}</p>
          {detail_card('UV index', f"{c['uv']['value']} - {c['uv']['level']}", h(c['uv']['guidance']), '#fff9df' if c['uv']['value'] >= 6 else '#f6faf1', '#e3d08d' if c['uv']['value'] >= 6 else '#cfd9c2')}
          {detail_card('Mosquito Index', f"{c['mosquito']['value']}/10 - {c['mosquito']['level']}", f"{h(c['mosquito']['guidance'])}<br>Estimated from weather: {h(', '.join(c['mosquito']['reasons'][:4]))}.", '#f3faf5', '#bfdcc8')}
          {detail_card('Rain', rain['headline'], h(rain['detail']), '#eef7fc' if rain['class_name'] != 'rain-none' else '#f4f9fb', '#b7d2e2')}
          {detail_card('Clothing', clothing['headline'], '<ul style="margin:8px 0 0 18px;padding:0;">' + ''.join(f'<li style="margin-bottom:6px;">{h(item)}</li>' for item in clothing['items']) + '</ul>', '#fff9df' if clothing['class_name'] in {'warm', 'hot'} else '#f6faf1', '#e3d08d' if clothing['class_name'] in {'warm', 'hot'} else '#cfd9c2')}
        </div>

        <div style="border:1px solid #d7ddd2;border-radius:8px;background:#ffffff;padding:16px;">
          <div style="color:#2f5b7c;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;">Now to evening</div>
          <h2 style="margin:4px 0 12px;font-size:20px;">Hourly stoplight</h2>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
              <tr style="text-align:left;color:#5f665d;">
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">Time</th>
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">Status</th>
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">Feels</th>
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">UV</th>
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">Mosq</th>
                <th style="padding:8px;border-bottom:1px solid #d7ddd2;">Rain</th>
              </tr>
            </thead>
            <tbody>{hourly_html}</tbody>
          </table>
        </div>
    """
    if dashboard_url:
        html_body += (
            f'<p style="margin-top:16px;"><a href="{h(dashboard_url)}" '
            'style="color:#2f5b7c;font-weight:800;">Open dashboard</a></p>'
        )

    html_body += """
        <p style="color:#5f665d;font-size:12px;margin-top:16px;">Practical planning aid only. Use your judgment and follow relevant health guidance.</p>
      </div>
    </div>
    """

    return subject, text, html_body


def should_send(force_send):
    if force_send:
        return True

    target_hour = int(os.environ.get("DAILY_EMAIL_HOUR", "9"))
    now = datetime.now(ZoneInfo(LOCATION["timezone"]))
    return now.hour == target_hour


def send_email(subject, text, html_body):
    required = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "MAIL_FROM",
        "MAIL_TO",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required mail settings: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = os.environ["MAIL_TO"]
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")

    port = int(os.environ["SMTP_PORT"])
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, context=context) as smtp:
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    else:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port) as smtp:
            smtp.starttls(context=context)
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    force_send = os.environ.get("FORCE_SEND", "").lower() == "true"
    if not args.dry_run and not should_send(force_send):
        target_hour = int(os.environ.get("DAILY_EMAIL_HOUR", "9"))
        print(f"Not {target_hour}:00 America/New_York; skipping.")
        return

    current, hours = fetch_forecast()
    subject, text, html_body = build_message(
        current, hours, os.environ.get("DASHBOARD_URL", "")
    )

    if args.dry_run:
        print(subject)
        print()
        print(text)
        return

    send_email(subject, text, html_body)
    print(f"Sent: {subject}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Daily weather email failed: {exc}", file=sys.stderr)
        sys.exit(1)
