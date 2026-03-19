import time
import requests
import anthropic
from datetime import datetime
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# ---------------------------------------------------------------------------
# River configuration
# ---------------------------------------------------------------------------

RIVERS = [
    {
        "id": "13190500",
        "name": "SF Boise River",
        "full_name": "South Fork Boise River at Anderson Ranch Dam",
        "lat": 43.5,
        "lon": -115.8,
    },
    {
        "id": "13183000",
        "name": "Owyhee River",
        "full_name": "Owyhee River Below Owyhee Dam, OR",
        "lat": 43.65,
        "lon": -117.23,
    },
    {
        "id": "13150430",
        "name": "Silver Creek",
        "full_name": "Silver Creek at Sportsman Access NR Picabo, ID",
        "lat": 43.3,
        "lon": -114.1,
    },
]

RIVER_MAP = {r["id"]: r for r in RIVERS}

# ---------------------------------------------------------------------------
# Static river guide & hatch data
# ---------------------------------------------------------------------------

# Hatch chart by river site_id → month (1-12) → list of patterns
HATCH_CHART = {
    "13190500": {
        1:  ["Midge #18-22", "Sculpin #2-12"],
        2:  ["Midge #18-22", "BWO #16-22"],
        3:  ["Midge #18-22", "BWO #16-22"],
        4:  ["Midge #18-22", "BWO #16-22"],
        5:  ["Midge #18-22", "Giant Salmonfly #10-14", "BWO #16-22"],
        6:  ["Giant Salmonfly #10-14", "Western Green Drake #10-14", "Spotted Caddis #10-14", "PMD #14-18", "Golden Stone #6-8"],
        7:  ["PMD #14-18", "Hopper #4-10", "Golden Stone #6-8", "Green Caddis #8-14", "Yellow Sally #10-16", "Brown Drake #8-10"],
        8:  ["Hopper #4-10", "Trico #18-22", "Beetle #10-20", "Ant #10-16", "BWO #16-22"],
        9:  ["BWO #16-22", "Flav #14-16", "Midge #18-22", "Hopper #4-10"],
        10: ["BWO #16-22", "Midge #18-22"],
        11: ["BWO #16-22", "Midge #18-22"],
        12: ["Midge #18-22", "Sculpin #2-12"],
    },
    "13183000": {
        1:  ["Midge #18-22", "BWO #16-20"],
        2:  ["Midge #18-22", "BWO #16-20"],
        3:  ["Skwala Stonefly (dark olive)", "Midge #18-22", "BWO #16-20"],
        4:  ["Skwala Stonefly", "PMD #16", "Midge #18-22"],
        5:  ["PMD #16", "Spotted Sedge Caddis", "Speckled Wing Quills"],
        6:  ["PMD #16", "Mahogany Dun", "Spotted Sedge Caddis", "Cranefly #6-8"],
        7:  ["Trico #18-22", "Hopper #4-10", "Ants & Beetles", "PMD #16"],
        8:  ["Trico #18-22", "Hopper #4-10", "Ants & Beetles"],
        9:  ["BWO #16-20", "Mahogany Dun"],
        10: ["BWO #16-20", "Midge #18-22"],
        11: ["BWO #16-20", "Midge #18-22"],
        12: ["Midge #18-22", "BWO #16-20"],
    },
    "13150430": {
        1:  ["Midge #18-22 (Griffith's Gnat, Palomino Midge)"],
        2:  ["Midge #18-22", "BWO #20-22 (Parachute Adams, Olive Sparkle Dun)"],
        3:  ["BWO #20-22", "Midge #18-22"],
        4:  ["BWO #20-22", "Midge #18-22"],
        5:  ["BWO #20-22", "PMD #16-18", "Caddis #14-16"],
        6:  ["PMD #16-18 (Yellow Sparkle Dun)", "Brown Drake #10 (Lawson's)", "Green Drake", "Caddis #14-16"],
        7:  ["Trico #20-22 (CDC Trico)", "Callibaetis #14-16", "Hopper/Terrestrials", "Caddis #14-16"],
        8:  ["Trico #20-22", "Callibaetis #16-18", "Hopper/Ants/Beetles", "PMD Cripple #16-20"],
        9:  ["BWO #20-22", "Trico #20-22", "PMD #16-18"],
        10: ["BWO #20-22 (Olive Sparkle Dun)", "Midge #18-22"],
        11: ["BWO #20-22", "Midge #18-22"],
        12: ["Midge #18-22"],
    },
}

RIVER_GUIDE = {
    "13190500": {
        "character": "Tailwater below Anderson Ranch Dam. Cold, consistent 46–48°F year-round. Technical midge and BWO fishery with exceptional stonefly and caddis hatches in summer. Bull trout present — handle with care and release quickly.",
        "techniques": "Euro/indicator nymphing with small midges and BWO emergers. Summer: sight fishing with dry flies at lower flows. Long leaders (5x–6x) and small flies (#20–24) for sipping fish. Oversized bead jig heads with small midge tags for Euro.",
        "species": "Rainbow & brown trout, bull trout",
        "notes": "Barbless required. Road/weather checks recommended in winter.",
    },
    "13183000": {
        "character": "Tailwater below Owyhee Dam (~10 miles of public water). Brown trout paradise averaging 14–17\", with fish to 10 lbs. Low-gradient slow pools and short riffles require precise drag-free drifts. Water often a milky green color.",
        "techniques": "Spring: Skwala and midge nymphs. Summer: dry fly during PMD/Trico hatches, hopper-dropper. Fall/Winter: streamer and midge nymph. Slow retrieves for big resident browns. Weekday visits avoid crowds.",
        "species": "Brown trout (dominant), rainbow trout. Browns spawn Oct–Nov — avoid spawning beds.",
        "notes": "~90 min west of Boise via I-84 and Hwy 201. Check ODFW for current regulations.",
    },
    "13150430": {
        "character": "World-class spring creek with ultra-clear water and highly selective wild trout. Requires stealth, fine tippets (5x–6x), and a precise drag-free presentation. Heavy angler pressure July–August — arrive early.",
        "techniques": "Dry fly during hatches (observe rises carefully before casting). Nymph when no surface activity. Terrestrials on windy summer days. Float tubes required in S-Turns section. Early morning and evening most productive.",
        "species": "Wild rainbow & brown trout. C&R fly fishing only, barbless hooks.",
        "notes": "Check in at Nature Conservancy visitor center at the Preserve. Some sections float-tube only.",
    },
}

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

_cache = {}
RIVER_TTL = 15 * 60    # 15 minutes
WEATHER_TTL = 60 * 60  # 60 minutes
REPORT_TTL = 4 * 60 * 60  # 4 hours

def cached(key, ttl, fetch_fn):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["data"]
    data = fetch_fn()
    _cache[key] = {"ts": time.time(), "data": data}
    return data


# ---------------------------------------------------------------------------
# USGS river flow
# ---------------------------------------------------------------------------

def fetch_usgs():
    site_ids = ",".join(r["id"] for r in RIVERS)
    url = (
        "https://waterservices.usgs.gov/nwis/iv/"
        f"?sites={site_ids}&parameterCd=00060,00010&format=json&period=P7D"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    result = {}
    for series in raw.get("value", {}).get("timeSeries", []):
        site_id = series["sourceInfo"]["siteCode"][0]["value"]
        param = series["variable"]["variableCode"][0]["value"]
        values = series["values"][0]["value"]

        parsed = []
        for v in values:
            try:
                parsed.append({"t": v["dateTime"], "v": float(v["value"])})
            except (ValueError, TypeError):
                continue

        if site_id not in result:
            result[site_id] = {}

        if param == "00060":
            result[site_id]["flow"] = parsed
            result[site_id]["current_cfs"] = parsed[-1]["v"] if parsed else None
        elif param == "00010":
            if parsed and parsed[-1]["v"] is not None:
                result[site_id]["water_temp_f"] = round(parsed[-1]["v"] * 9 / 5 + 32, 1)

    return result


# ---------------------------------------------------------------------------
# Open-Meteo weather & barometric pressure
# ---------------------------------------------------------------------------

def fetch_weather(site_id):
    river = RIVER_MAP[site_id]
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={river['lat']}&longitude={river['lon']}"
        "&hourly=surface_pressure,temperature_2m,precipitation,wind_speed_10m"
        "&temperature_unit=fahrenheit"
        "&wind_speed_unit=mph"
        "&precipitation_unit=inch"
        "&past_days=7&forecast_days=1&timezone=America%2FBoise"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    pressures = hourly.get("surface_pressure", [])
    temps = hourly.get("temperature_2m", [])
    precip = hourly.get("precipitation", [])
    wind = hourly.get("wind_speed_10m", [])

    def to_inhg(hpa):
        return round(hpa * 0.02953, 2) if hpa is not None else None

    pressure_inhg = [to_inhg(p) for p in pressures]
    current_pressure = next((p for p in reversed(pressure_inhg) if p is not None), None)

    trend = "Steady"
    if len(pressures) >= 4:
        recent = next((p for p in reversed(pressures) if p is not None), None)
        older = next((p for p in reversed(pressures[:-3]) if p is not None), None)
        if recent is not None and older is not None:
            diff = recent - older
            if diff > 1:
                trend = "Rising"
            elif diff < -1:
                trend = "Falling"

    past_temps = [t for t in temps if t is not None]
    past_precip = [p for p in precip if p is not None]
    past_wind = [w for w in wind if w is not None]

    return {
        "times": times,
        "pressure_inhg": pressure_inhg,
        "current_pressure_inhg": current_pressure,
        "pressure_trend": trend,
        "temp_min_f": round(min(past_temps), 1) if past_temps else None,
        "temp_max_f": round(max(past_temps), 1) if past_temps else None,
        "precip_total_in": round(sum(past_precip), 2) if past_precip else 0,
        "wind_avg_mph": round(sum(past_wind) / len(past_wind), 1) if past_wind else None,
    }


# ---------------------------------------------------------------------------
# AI fishing report generation
# ---------------------------------------------------------------------------

def generate_report(site_id):
    """Generate a fishing report using Claude based on live flow and weather data."""
    river = RIVER_MAP[site_id]
    guide = RIVER_GUIDE.get(site_id, {})
    month = datetime.now().month
    month_name = datetime.now().strftime("%B")
    hatches = HATCH_CHART.get(site_id, {}).get(month, [])

    # Fetch live data to inform the report
    try:
        usgs = fetch_usgs()
        river_data = usgs.get(site_id, {})
        flow = river_data.get("current_cfs")
        water_temp = river_data.get("water_temp_f")
    except Exception:
        flow, water_temp = None, None

    try:
        weather = fetch_weather(site_id)
        pressure = weather.get("current_pressure_inhg")
        pressure_trend = weather.get("pressure_trend")
        temp_min = weather.get("temp_min_f")
        temp_max = weather.get("temp_max_f")
        precip = weather.get("precip_total_in", 0)
        wind = weather.get("wind_avg_mph")
    except Exception:
        pressure = pressure_trend = temp_min = temp_max = wind = None
        precip = 0

    prompt = f"""You are an expert fly fishing guide writing a current fishing report for {river['full_name']}.

Current conditions:
- Flow: {flow} CFS
- Water temperature: {water_temp}°F
- Air temp range (past 7 days): {temp_min}–{temp_max}°F
- Barometric pressure: {pressure} inHg ({pressure_trend})
- Precipitation (past 7 days): {precip} inches
- Wind avg: {wind} mph
- Month: {month_name}
- Active hatches: {', '.join(hatches) if hatches else 'None listed'}

River character: {guide.get('character', '')}
Recommended techniques: {guide.get('techniques', '')}
Species: {guide.get('species', '')}
Notes: {guide.get('notes', '')}

Write a 3–4 sentence fishing report in the style of a knowledgeable local guide. Be specific about current flows, expected hatches, recommended flies, and tactics. Keep it practical and concise."""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text

    return {
        "text": text,
        "source": "AI Report",
        "date": datetime.now().strftime("%B %-d, %Y"),
        "url": None,
    }


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", rivers=RIVERS)


@app.route("/api/rivers")
def api_rivers():
    try:
        usgs = cached("usgs_all", RIVER_TTL, fetch_usgs)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    result = []
    for river in RIVERS:
        site_id = river["id"]
        data = usgs.get(site_id, {})
        result.append({
            "id": site_id,
            "name": river["name"],
            "full_name": river["full_name"],
            "current_cfs": data.get("current_cfs"),
            "water_temp_f": data.get("water_temp_f"),
            "flow_history": data.get("flow", []),
        })

    return jsonify(result)


@app.route("/api/weather/<site_id>")
def api_weather(site_id):
    if site_id not in RIVER_MAP:
        return jsonify({"error": "Unknown site"}), 404
    try:
        data = cached(f"weather_{site_id}", WEATHER_TTL, lambda: fetch_weather(site_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(data)


@app.route("/api/weather-all")
def api_weather_all():
    result = {}
    for river in RIVERS:
        site_id = river["id"]
        try:
            data = cached(f"weather_{site_id}", WEATHER_TTL, lambda s=site_id: fetch_weather(s))
            result[site_id] = data
        except Exception as e:
            result[site_id] = {"error": str(e)}
        time.sleep(0.5)
    return jsonify(result)


@app.route("/api/reports/<site_id>")
def api_reports(site_id):
    if site_id not in RIVER_MAP:
        return jsonify({"error": "Unknown site"}), 404

    try:
        live_report = cached(f"report_{site_id}", REPORT_TTL, lambda: generate_report(site_id))
    except Exception as e:
        print(f"Report generation error ({site_id}): {e}")
        live_report = None

    month = datetime.now().month
    return jsonify({
        "live_report": live_report,
        "current_hatch": HATCH_CHART.get(site_id, {}).get(month, []),
        "guide": RIVER_GUIDE.get(site_id, {}),
        "month_name": datetime.now().strftime("%B"),
    })


if __name__ == "__main__":
    app.run(debug=False, port=5001)
