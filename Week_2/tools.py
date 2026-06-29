"""
Tool definitions for the Weather & News Agent.

Each tool has:
  - A Python implementation that calls a real API
  - A JSON schema used by Groq to know when/how to call it

APIs used (both free, no key required):
  Weather: wttr.in
  News:    Hacker News via Algolia search (hn.algolia.com)
"""

import json
import requests

# ── JSON schemas (tell Groq what tools exist and how to call them) ─────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get current real-time weather for a city. "
                "Returns temperature, conditions, humidity, wind speed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'London' or 'New York'",
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial"],
                        "description": "Temperature units: metric (Celsius) or imperial (Fahrenheit). Default: metric.",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": (
                "Search recent news/tech articles on any topic via Hacker News. "
                "Returns titles, URLs, scores, and authors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic to search, e.g. 'AI research' or 'climate change'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of articles to return (1–5). Default: 3.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ── Tool implementations ────────────────────────────────────────────────────────

def get_weather(city: str, units: str = "metric") -> dict:
    """Fetch current weather from wttr.in — no API key required."""
    try:
        resp = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        current = data["current_condition"][0]
        area    = data["nearest_area"][0]

        if units == "imperial":
            temp       = current["temp_F"]
            feels_like = current["FeelsLikeF"]
            unit_label = "°F"
        else:
            temp       = current["temp_C"]
            feels_like = current["FeelsLikeC"]
            unit_label = "°C"

        return {
            "city":        f"{area['areaName'][0]['value']}, {area['country'][0]['value']}",
            "temperature": f"{temp}{unit_label}",
            "feels_like":  f"{feels_like}{unit_label}",
            "condition":   current["weatherDesc"][0]["value"],
            "humidity":    f"{current['humidity']}%",
            "wind_speed":  f"{current['windspeedKmph']} km/h",
            "visibility":  f"{current['visibility']} km",
        }
    except requests.RequestException as e:
        return {"error": f"Weather API request failed: {e}"}
    except (KeyError, IndexError, ValueError) as e:
        return {"error": f"Weather data parse error: {e}"}


def get_news(query: str, max_results: int = 3) -> dict:
    """Search Hacker News articles via Algolia API — no API key required."""
    max_results = max(1, min(max_results, 5))
    try:
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": max_results},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        articles = [
            {
                "title":    hit.get("title", "No title"),
                "url":      hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "score":    hit.get("points", 0),
                "author":   hit.get("author", "unknown"),
                "posted":   hit.get("created_at", ""),
                "comments": hit.get("num_comments", 0),
            }
            for hit in data["hits"]
        ]

        return {
            "query":         query,
            "total_results": data["nbHits"],
            "articles":      articles,
        }
    except requests.RequestException as e:
        return {"error": f"News API request failed: {e}"}
    except (KeyError, ValueError) as e:
        return {"error": f"News data parse error: {e}"}


# ── Dispatch table (maps function name → callable) ─────────────────────────────

TOOL_DISPATCH = {
    "get_weather": get_weather,
    "get_news":    get_news,
}
