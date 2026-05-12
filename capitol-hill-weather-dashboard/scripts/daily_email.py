#!/usr/bin/env python3
import argparse
import html
import json
import math
import os
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

LOCATION = {
    "name": "Capitol Hill, DC",
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
            "layers, and check his neck, chest, hands, and mood often."
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
            "the cautious infant range."
        ),
    },
}

THUNDERSTORM_CODES = {95, 96, 99}
HEAVY_PRECIP_CODES = {65, 67, 75, 77, 82, 86}


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


def classify(hour):
    temp_f = round(hour["temperature"])
    humidity = round(hour["humidity"])
    wind_mph = round(hour["wind_speed"])
    uv_index = hour.get("uv_index") or 0
    precipitation = hour.get("precipitation") or 0
    weather_code = int(hour.get("weather_code") or 0)
    feels, method, heat_index, wind_chill = feels_like(temp_f, humidity, wind_mph)
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
        reasons.append(f"UV index is {round(uv_index)} during warm weather")

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
            reasons.append(f"UV index is {round(uv_index)}")
        if precipitation >= 0.05:
            status = "yellow"
            reasons.append("rain likely")

    if not reasons:
        reasons.append(
            "temperature, humidity, wind, and precipitation are in the cautious infant range"
        )

    return {
        **STATUS[status],
        "status": status,
        "temp_f": temp_f,
        "humidity": humidity,
        "wind_mph": wind_mph,
        "uv_index": uv_index,
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


def best_window(hours):
    best = []
    current = []
    for hour in hours:
        if hour["classification"]["status"] == "green":
            current.append(hour)
        else:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current

    if not best:
        return "No green windows left today."

    start = best[0]["time"].strftime("%-I %p")
    end_dt = best[-1]["time"].replace(hour=best[-1]["time"].hour + 1)
    end = end_dt.strftime("%-I %p")
    average = round(
        sum(hour["classification"]["feels_like"] for hour in best) / len(best)
    )
    return f"{start}-{end}, avg feels {average}F"


def build_message(current, hours, dashboard_url):
    c = current["classification"]
    local_time = datetime.now(ZoneInfo(LOCATION["timezone"])).strftime("%A, %B %-d at %-I:%M %p")
    reason_lines = "\n".join(f"- {reason}" for reason in c["reasons"])
    hourly_lines = [
        f"{hour['time'].strftime('%-I %p')}: {hour['classification']['label']} "
        f"({hour['classification']['feels_like']}F feels-like)"
        for hour in hours[:10]
    ]

    subject = f"Capitol Hill baby weather: {c['label']} ({c['feels_like']}F feels-like)"
    text = f"""Capitol Hill infant weather
{local_time}

Right now: {c['label']} - {c['tone']}
Temp: {c['temp_f']}F
Feels like: {c['feels_like']}F ({c['feels_like_method']})
Humidity: {c['humidity']}%
Wind: {c['wind_mph']} mph

Recommendation:
{c['recommendation']}

Why:
{reason_lines}

Best window:
{best_window(hours)}

Hourly:
{chr(10).join(hourly_lines)}
"""

    if dashboard_url:
        text += f"\nDashboard: {dashboard_url}\n"

    html_body = f"""
    <h1>Capitol Hill infant weather</h1>
    <p>{html.escape(local_time)}</p>
    <h2>{html.escape(c['label'])}: {html.escape(c['tone'])}</h2>
    <p><strong>{c['feels_like']}F feels-like</strong> ({html.escape(c['feels_like_method'])})</p>
    <p>Temp {c['temp_f']}F | Humidity {c['humidity']}% | Wind {c['wind_mph']} mph</p>
    <p>{html.escape(c['recommendation'])}</p>
    <h3>Why</h3>
    <ul>{''.join(f'<li>{html.escape(reason)}</li>' for reason in c['reasons'])}</ul>
    <h3>Best window</h3>
    <p>{html.escape(best_window(hours))}</p>
    <h3>Hourly</h3>
    <ul>{''.join(f'<li>{html.escape(line)}</li>' for line in hourly_lines)}</ul>
    """
    if dashboard_url:
        html_body += f'<p><a href="{html.escape(dashboard_url)}">Open dashboard</a></p>'

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
