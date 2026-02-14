"""Weather command: current conditions and forecast via Open-Meteo.

Handles:
    "what's the weather"
    "what's the forecast"
    "what's the temperature"
    "is it going to rain"
    "what's the weather tomorrow"
"""

import json
import re
import urllib.request

from hecko.commands.parse import Parse

# Tucson, AZ (85718)
_LAT = 32.22174
_LON = -110.92648
_LOCATION = "Tucson"
_TIMEZONE = "America/Phoenix"

# WMO weather codes to descriptions
_WMO_CODES = {
    0: "clear skies",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy with frost",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with heavy hail",
}


def _fetch_weather():
    """Fetch current weather and 3-day forecast from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={_LAT}&longitude={_LON}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        f"weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone={_TIMEZONE}&forecast_days=3"
    )
    resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
    return resp


def _describe_weather_code(code):
    return _WMO_CODES.get(code, "unknown conditions")


_FORECAST_WORDS = re.compile(r"\b(tomorrow|forecast|next few days|later this week)\b", re.IGNORECASE)
_RAIN_WORDS = re.compile(r"\b(rain|snow|precipitation|umbrella|storm)\b", re.IGNORECASE)
_CURRENT_WORDS = re.compile(r"\b(weather|temperature|temp|outside|how hot|how cold|how warm)\b", re.IGNORECASE)


def _classify(text):
    """Classify: 'current', 'forecast', 'rain', or None."""
    if _FORECAST_WORDS.search(text):
        return "forecast"
    if _RAIN_WORDS.search(text):
        return "rain"
    if _CURRENT_WORDS.search(text):
        return "current"
    return None


def parse(text):
    cls = _classify(text)
    if cls is None:
        return None
    command_map = {"current": "current_weather", "forecast": "forecast", "rain": "rain_check"}
    return Parse(command=command_map[cls], score=0.9)


def handle(p):
    try:
        data = _fetch_weather()
    except Exception as e:
        return f"Sorry, I couldn't get the weather. {e}"

    current = data["current"]
    daily = data["daily"]

    temp = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])
    humidity = current["relative_humidity_2m"]
    wind = round(current["wind_speed_10m"])
    conditions = _describe_weather_code(current["weather_code"])

    if p.command == "current_weather":
        response = (
            f"It's currently {temp} degrees in {_LOCATION} with {conditions}. "
            f"Feels like {feels_like}. "
        )
        if wind > 5:
            response += f"Wind at {wind} miles per hour. "
        hi = round(daily["temperature_2m_max"][0])
        lo = round(daily["temperature_2m_min"][0])
        response += f"Today's high is {hi}, low {lo}."
        return response

    elif p.command == "forecast":
        _DAYS = ["Today", "Tomorrow", "The day after"]
        parts = []
        for i in range(3):
            hi = round(daily["temperature_2m_max"][i])
            lo = round(daily["temperature_2m_min"][i])
            cond = _describe_weather_code(daily["weather_code"][i])
            precip = daily["precipitation_probability_max"][i]
            part = f"{_DAYS[i]}: {cond}, high of {hi}, low of {lo}"
            if precip > 20:
                part += f", {precip} percent chance of precipitation"
            parts.append(part)
        return ". ".join(parts) + "."

    elif p.command == "rain_check":
        precip_today = daily["precipitation_probability_max"][0]
        precip_tomorrow = daily["precipitation_probability_max"][1]
        if precip_today > 50:
            response = f"Yes, there's a {precip_today} percent chance of rain today. "
        elif precip_today > 20:
            response = f"Maybe. There's a {precip_today} percent chance of rain today. "
        else:
            response = f"It doesn't look like it. Only a {precip_today} percent chance today. "
        if precip_tomorrow > 30:
            response += f"Tomorrow has a {precip_tomorrow} percent chance."
        return response

    return f"It's currently {temp} degrees with {conditions}."
