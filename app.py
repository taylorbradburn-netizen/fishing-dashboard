import os
import time
import requests
import anthropic
from datetime import datetime, timedelta, timezone, date
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

ROAD_ACCESS = {
    "13190500": {
        "access_road": "South Fork Road (USFS Rd 61) off Hwy 20 near Pine, ID",
        "agency": "Boise National Forest (USFS)",
        "notes": "Paved to Anderson Ranch Dam. Upper canyon spur roads are unpaved and may require high-clearance in spring. Gates on upper sections close Nov–Apr.",
        "conditions_url": "https://www.fs.usda.gov/boise",
    },
    "13183000": {
        "access_road": "Owyhee Reservoir Road off Hwy 201 near Adrian, OR",
        "agency": "BLM Vale District",
        "notes": "Paved to dam, dirt BLM roads beyond. Remote canyon access (Rome, Three Forks) requires high-clearance 4WD. Flash flood risk on canyon roads in spring.",
        "conditions_url": "https://www.blm.gov/office/vale-district-office",
    },
    "13150430": {
        "access_road": "Kilpatrick Road off Hwy 20 near Picabo, ID",
        "agency": "The Nature Conservancy",
        "notes": "Hwy 20 is paved year-round. Preserve access roads are gravel. Must check in at the Nature Conservancy visitor center. Some sections are float-tube only.",
        "conditions_url": "https://www.nature.org/en-us/get-involved/how-to-help/places-we-protect/silver-creek-preserve/",
    },
}

# ---------------------------------------------------------------------------
# Fishing regulations & seasonal closures
# Source: IDFG 2025-2027 Fishing Seasons and Rules / ODFW 2026 Regulations
# ---------------------------------------------------------------------------

REGULATIONS = {
    "13190500": {
        "season": "Saturday of Memorial Day weekend through March 31",
        "closures": [{"type": "apr1_to_memorial_day_sat"}],
        "restrictions": "Artificial flies and lures only. Catch and release for bull trout.",
        "source_url": "https://idfg.idaho.gov/rules/fish",
    },
    "13183000": {
        "restrictions": "Fly fishing only section near dam. Check ODFW for current rules.",
        "source_url": "https://myodfw.com/fishing/regulations",
    },
    "13150430": {
        "restrictions": "Artificial flies only. Catch and release. Float tubes only above Hwy 20 bridge near MP 187.2.",
        "source_url": "https://idfg.idaho.gov/rules/fish",
        "reg_sections": [
            {"name": "Mouth to Hwy 20 bridge (MP 187.2)", "dates": "Open all year"},
            {"name": "Hwy 20 bridge (MP 187.2) to Grove/Stalker Creek confluence", "dates": "Open: Sat of Memorial Day weekend – Nov 30 · Closed: Dec 1 – Fri before Memorial Day"},
            {"name": "Kilpatrick Pond dam to Kilpatrick Bridge", "dates": "Open: Sat of Memorial Day weekend – Mar 31 · Closed: Apr 1 – Fri before Memorial Day"},
        ],
    },
}


def _memorial_day_saturday(year):
    """Saturday of Memorial Day weekend (Saturday before Memorial Day Monday)."""
    d = date(year, 5, 31)
    while d.weekday() != 0:  # find last Monday in May
        d -= timedelta(days=1)
    return d - timedelta(days=2)


def check_regulation_closure(site_id):
    regs = REGULATIONS.get(site_id, {})
    today = date.today()
    is_closed = False
    closure_reason = None

    for rule in regs.get("closures", []):
        if rule["type"] == "apr1_to_memorial_day_sat":
            open_date = _memorial_day_saturday(today.year)
            close_start = date(today.year, 4, 1)
            if close_start <= today < open_date:
                is_closed = True
                closure_reason = f"Closed — season opens {open_date.strftime('%B %-d, %Y')}"

    return {
        "is_closed": is_closed,
        "closure_reason": closure_reason,
        "season": regs.get("season", "Year-round"),
        "restrictions": regs.get("restrictions", ""),
        "source_url": regs.get("source_url", ""),
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
RIVER_TTL = 15 * 60       # 15 minutes
WEATHER_TTL = 60 * 60     # 60 minutes
REPORT_TTL = 4 * 60 * 60  # 4 hours
TRAFFIC_TTL = 15 * 60     # 15 minutes

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
    lat, lon = river["lat"], river["lon"]
    headers = {"User-Agent": "fishing-dashboard/1.0"}

    # Resolve NWS grid and observation stations
    r = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=15)
    r.raise_for_status()
    props = r.json()["properties"]

    # Gridpoint data for temperature, wind, precipitation
    r = requests.get(props["forecastGridData"], headers=headers, timeout=30)
    r.raise_for_status()
    grid = r.json()["properties"]

    def parse_vals(key, convert=None):
        out = []
        for v in grid.get(key, {}).get("values", []):
            val = v.get("value")
            if val is not None:
                out.append(convert(val) if convert else val)
        return out

    temps_f    = parse_vals("temperature",               lambda c: round(c * 9/5 + 32, 1))
    winds_mph  = parse_vals("windSpeed",                 lambda k: round(k * 0.621371, 1))
    precips_in = parse_vals("quantitativePrecipitation", lambda mm: mm * 0.0393701)

    # Observation station pressure history (7 days)
    stations_r = requests.get(props["observationStations"], headers=headers, timeout=15)
    stations_r.raise_for_status()
    station_id = stations_r.json()["features"][0]["properties"]["stationIdentifier"]

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    obs_url = (
        f"https://api.weather.gov/stations/{station_id}/observations"
        f"?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&end={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=168"
    )
    obs_r = requests.get(obs_url, headers=headers, timeout=15)
    obs_r.raise_for_status()
    observations = list(reversed(obs_r.json()["features"]))  # oldest first

    press_inhg, times = [], []
    for obs in observations:
        p = obs["properties"].get("barometricPressure", {}).get("value")
        t = obs["properties"].get("timestamp")
        if p is not None and t:
            press_inhg.append(round(p * 0.0002953, 2))
            times.append(t)

    current_pressure = press_inhg[-1] if press_inhg else None
    trend = "Steady"
    if len(press_inhg) >= 4:
        diff = press_inhg[-1] - press_inhg[-4]
        if diff > 0.02:
            trend = "Rising"
        elif diff < -0.02:
            trend = "Falling"

    return {
        "times": times,
        "pressure_inhg": press_inhg,
        "current_pressure_inhg": current_pressure,
        "pressure_trend": trend,
        "temp_min_f": round(min(temps_f), 1) if temps_f else None,
        "temp_max_f": round(max(temps_f), 1) if temps_f else None,
        "precip_total_in": round(sum(precips_in), 2) if precips_in else 0,
        "wind_avg_mph": round(sum(winds_mph) / len(winds_mph), 1) if winds_mph else None,
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
# Traffic conditions (TomTom Traffic Incidents + Routing API)
# ---------------------------------------------------------------------------

# Idaho Angler fly shop, Boise, ID
ORIGIN_LAT = 43.594
ORIGIN_LON = -116.213
ORIGIN_NAME = "Idaho Angler (Boise)"


def fetch_traffic(site_id):
    """Fetch real-time traffic incidents and drive time from Idaho Angler via TomTom."""
    access = ROAD_ACCESS.get(site_id, {})
    river = RIVER_MAP[site_id]

    api_key = os.environ.get("TOMTOM_API_KEY", "")
    if not api_key:
        return {
            "text": "No traffic data — set TOMTOM_API_KEY to enable.",
            "incidents": [],
            "drive_time_min": None,
            "origin": ORIGIN_NAME,
            "access_road": access.get("access_road"),
            "agency": access.get("agency"),
            "conditions_url": access.get("conditions_url"),
        }

    lat, lon = river["lat"], river["lon"]
    delta = 0.3  # ~15–20 mile radius

    # Fetch incidents and drive time in parallel
    fields = "{incidents{properties{iconCategory,magnitudeOfDelay,events{description},from,to,roadNumbers,delay}}}"

    incidents_resp = requests.get(
        "https://api.tomtom.com/traffic/services/5/incidentDetails",
        params={
            "key": api_key,
            "bbox": f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}",
            "fields": fields,
            "language": "en-GB",
            "timeValidityFilter": "present",
        },
        timeout=15,
    )
    incidents_resp.raise_for_status()

    route_resp = requests.get(
        f"https://api.tomtom.com/routing/1/calculateRoute/{ORIGIN_LAT},{ORIGIN_LON}:{lat},{lon}/json",
        params={
            "key": api_key,
            "traffic": "true",
            "travelMode": "car",
        },
        timeout=15,
    )
    route_resp.raise_for_status()

    # Parse incidents
    incidents = []
    for inc in incidents_resp.json().get("incidents", []):
        props = inc.get("properties", {})
        events = props.get("events", [])
        desc = events[0].get("description", "") if events else ""
        if not desc:
            continue
        roads = props.get("roadNumbers", [])
        delay = props.get("delay") or 0
        incidents.append({
            "description": desc,
            "from": props.get("from", ""),
            "to": props.get("to", ""),
            "road": ", ".join(roads) if roads else "",
            "delay_min": round(delay / 60) if delay else 0,
            "magnitude": props.get("magnitudeOfDelay", 0),
        })

    # Parse drive time (seconds → minutes)
    drive_time_min = None
    try:
        summary = route_resp.json()["routes"][0]["summary"]
        drive_time_min = round(summary["travelTimeInSeconds"] / 60)
    except (KeyError, IndexError):
        pass

    # Build summary text
    parts = []
    if drive_time_min is not None:
        parts.append(f"{drive_time_min} min drive from {ORIGIN_NAME}")
    if not incidents:
        parts.append("no incidents on route")
    else:
        for inc in incidents[:3]:
            line = inc["description"]
            if inc["road"]:
                line += f" on {inc['road']}"
            if inc["from"] and inc["to"]:
                line += f" ({inc['from']} to {inc['to']})"
            if inc["delay_min"] > 0:
                line += f" — {inc['delay_min']} min delay"
            parts.append(line)

    text = ". ".join(parts).capitalize() + "."

    return {
        "text": text,
        "incidents": incidents,
        "drive_time_min": drive_time_min,
        "origin": ORIGIN_NAME,
        "access_road": access.get("access_road"),
        "agency": access.get("agency"),
        "conditions_url": access.get("conditions_url"),
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
        "regulations": {
            **check_regulation_closure(site_id),
            "reg_sections": REGULATIONS.get(site_id, {}).get("reg_sections", []),
        },
    })


@app.route("/api/road-access/<site_id>")
def api_road_access(site_id):
    if site_id not in RIVER_MAP:
        return jsonify({"error": "Unknown site"}), 404
    try:
        data = cached(f"traffic_{site_id}", TRAFFIC_TTL, lambda: fetch_traffic(site_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=False, port=5001)
