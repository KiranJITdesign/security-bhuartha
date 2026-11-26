"""Real geospatial layers: Official MarineRegions Indian EEZ, GFW Offshore Infra & Maritime Zones."""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REAL_EEZ_PATH = DATA_DIR / "indian_eez_real.geojson"
REAL_INFRA_PATH = DATA_DIR / "india_offshore_infra_real.json"

EARTH_RADIUS_KM = 6371.0
NM_PER_KM = 0.539957

# Standard ITU Maritime Identification Digits (MID) country prefix table
ITU_MID_COUNTRY = {
    "419": "India",
    "405": "Bangladesh",
    "417": "Sri Lanka",
    "455": "Maldives",
    "463": "Pakistan",
    "477": "Hong Kong",
    "412": "China",
    "413": "China",
    "414": "China",
    "563": "Singapore",
    "564": "Singapore",
    "565": "Singapore",
    "566": "Singapore",
    "567": "Thailand",
    "533": "Malaysia",
    "525": "Indonesia",
    "538": "Marshall Islands",
    "636": "Liberia",
    "351": "Panama",
    "352": "Panama",
    "353": "Panama",
    "354": "Panama",
    "355": "Panama",
    "356": "Panama",
    "357": "Panama",
    "370": "Panama",
    "371": "Panama",
    "372": "Panama",
    "373": "Panama",
    "229": "Malta",
    "248": "Malta",
    "249": "Malta",
    "244": "Netherlands",
    "245": "Netherlands",
    "246": "Netherlands",
    "325": "Dominica",
    "572": "Tuvalu",
    "215": "Malta",
    "255": "Portugal",
    "257": "Norway",
    "431": "Japan",
    "440": "South Korea",
    "470": "UAE",
    "309": "Bahamas",
    "311": "Bahamas",
}

_EEZ_CACHE: Dict = {}
_EEZ_POINTS_RAD: np.ndarray = np.empty((0, 2))
_INFRA_CACHE: List[Dict] = []


def mmsi_to_flag(mmsi: str) -> str:
    """Resolve real ITU MID country prefix from a 9-digit MMSI."""
    if not mmsi or len(str(mmsi)) < 3:
        return "Unknown Flag"
    return ITU_MID_COUNTRY.get(str(mmsi)[:3], f"MID-{str(mmsi)[:3]}")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in kilometers between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _point_to_segment_km(
    lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    cos_lat = math.cos(math.radians(lat))
    px, py = lon * cos_lat, lat
    ax, ay = lon1 * cos_lat, lat1
    bx, by = lon2 * cos_lat, lat2
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < 1e-12:
        return haversine_km(lat, lon, lat1, lon1)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    proj_lon = (ax + t * dx) / (cos_lat if abs(cos_lat) > 1e-6 else 1.0)
    proj_lat = ay + t * dy
    return haversine_km(lat, lon, proj_lat, proj_lon)


def _point_in_polygon(lat: float, lon: float, polygon_coords: List[List[float]]) -> bool:
    inside = False
    n = len(polygon_coords)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) if abs(yj - yi) > 1e-12 else 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


# Offline Coastline backup polygons [lon, lat]
INDIA_MAINLAND_COAST = [
    [68.18, 23.75], [68.80, 23.20], [69.05, 22.85], [70.20, 22.95], [69.60, 22.45],
    [68.95, 22.25], [69.60, 21.62], [70.36, 20.90], [70.98, 20.72], [72.15, 21.75],
    [72.62, 22.28], [72.92, 21.45], [72.80, 20.40], [72.76, 19.35], [72.82, 18.95],
    [73.05, 18.10], [73.30, 17.00], [73.68, 15.85], [73.95, 15.10], [74.42, 14.15],
    [74.82, 12.90], [75.35, 11.88], [75.78, 11.25], [76.22, 9.96], [76.58, 8.88],
    [77.54, 8.08], [78.15, 8.78], [79.15, 9.28], [79.85, 10.28], [79.82, 11.75],
    [80.28, 13.08], [80.15, 14.50], [80.25, 15.85], [81.18, 15.95], [82.25, 16.95],
    [83.30, 17.70], [84.90, 19.25], [85.85, 19.82], [86.68, 20.26], [87.05, 20.85],
    [87.62, 21.52], [88.25, 21.65], [89.05, 21.70], [89.15, 24.10], [84.50, 25.50],
    [77.20, 28.60], [71.10, 25.20], [68.18, 23.75],
]

SRI_LANKA_COAST = [
    [79.85, 9.65], [80.75, 9.30], [81.25, 8.55], [81.85, 7.40], [81.20, 6.12],
    [80.20, 5.95], [79.82, 6.92], [79.72, 8.20], [79.85, 9.65],
]

NORTH_ANDAMAN_COAST = [
    [92.85, 13.55], [93.08, 13.20], [92.98, 12.50], [92.72, 11.65],
    [92.58, 11.55], [92.62, 12.35], [92.85, 13.55],
]

GREAT_NICOBAR_COAST = [
    [93.62, 7.25], [93.92, 7.05], [93.85, 6.75], [93.65, 6.82], [93.62, 7.25],
]

SHIPPING_LANES = [
    {
        "name": "Arabian Sea International Transit Corridor",
        "coords": [[63.5, 21.8], [67.8, 19.6], [70.9, 15.2], [73.4, 10.6], [76.2, 7.6], [80.5, 5.8]],
    },
    {
        "name": "West Coast Coastal Shipping Lane (Kandla-Mumbai-Mangaluru-Cochin)",
        "coords": [[69.5, 22.4], [72.2, 18.9], [73.1, 17.0], [74.4, 12.9], [75.8, 9.8]],
    },
    {
        "name": "Bay of Bengal Main Maritime Corridor (Chennai-Paradip-Haldia)",
        "coords": [[80.5, 5.8], [81.6, 12.8], [84.6, 17.5], [87.4, 20.1], [88.3, 21.4]],
    },
    {
        "name": "Six Degree Channel (Great Nicobar - Malacca Approach)",
        "coords": [[80.5, 5.8], [88.0, 6.0], [93.8, 6.1], [96.8, 6.1]],
    },
]

RESTRICTED_ZONES = [
    {
        "name": "Bombay High Offshore Energy Protection Zone",
        "zone_type": "Offshore Hydrocarbon Exclusion Zone",
        "coords": [[70.75, 19.75], [72.20, 19.75], [72.20, 18.65], [70.75, 18.65], [70.75, 19.75]],
    },
    {
        "name": "Sundarbans & Northern Bay Coastal Sanctuary Buffer",
        "zone_type": "Coastal Ecological & Fishery Buffer",
        "coords": [[88.10, 21.70], [89.40, 21.70], [89.40, 21.05], [88.10, 21.05], [88.10, 21.70]],
    },
    {
        "name": "Lakshadweep Sovereign Coral & Fishery Zone",
        "zone_type": "Restricted Fishery Conservation Zone",
        "coords": [[71.60, 13.10], [73.30, 13.10], [73.30, 9.85], [71.60, 9.85], [71.60, 13.10]],
    },
    {
        "name": "Great Nicobar & Six Degree Chokepoint Buffer",
        "zone_type": "Strategic Island & Maritime Sanctuary Buffer",
        "coords": [[93.30, 7.20], [94.40, 7.20], [94.40, 6.05], [93.30, 6.05], [93.30, 7.20]],
    },
]

MAJOR_INDIAN_PORTS = [
    {"name": "Mumbai Port / JNPT", "infra_type": "Major Port", "lat": 18.95, "lon": 72.93},
    {"name": "New Mangalore Port", "infra_type": "Major Port", "lat": 12.92, "lon": 74.81},
    {"name": "Haldia / Syama Prasad Mookerjee Port", "infra_type": "Major Port", "lat": 22.02, "lon": 88.06},
    {"name": "Paradip Strategic Energy Port", "infra_type": "Major Port", "lat": 20.26, "lon": 86.67},
    {"name": "Campbell Bay (Great Nicobar) ICG Post", "infra_type": "ICG Node", "lat": 7.01, "lon": 93.93},
]


def _load_real_eez() -> Dict:
    global _EEZ_CACHE, _EEZ_POINTS_RAD
    if _EEZ_CACHE:
        return _EEZ_CACHE
    if REAL_EEZ_PATH.exists():
        data = json.loads(REAL_EEZ_PATH.read_text(encoding="utf-8"))
        pts = []
        for feat in data.get("features", []):
            geom = feat.get("geometry", {})
            if geom.get("type") == "MultiPolygon":
                for poly in geom.get("coordinates", []):
                    for ring in poly:
                        for lon, lat in ring[::3]:
                            pts.append([math.radians(lat), math.radians(lon)])
        if pts:
            _EEZ_POINTS_RAD = np.array(pts, dtype=float)
        _EEZ_CACHE = data
        return _EEZ_CACHE
    return {"type": "FeatureCollection", "features": []}


def _load_real_infra() -> List[Dict]:
    global _INFRA_CACHE
    if _INFRA_CACHE:
        return _INFRA_CACHE
    if REAL_INFRA_PATH.exists():
        _INFRA_CACHE = json.loads(REAL_INFRA_PATH.read_text(encoding="utf-8"))
    return _INFRA_CACHE


def get_indian_coastline_geojson() -> Dict:
    """Return Indian coastline & island polygons for offline resilience."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "India Mainland Coastline", "kind": "coastline"}, "geometry": {"type": "Polygon", "coordinates": [INDIA_MAINLAND_COAST]}},
            {"type": "Feature", "properties": {"name": "Sri Lanka Reference", "kind": "coastline"}, "geometry": {"type": "Polygon", "coordinates": [SRI_LANKA_COAST]}},
            {"type": "Feature", "properties": {"name": "Andaman Islands", "kind": "coastline"}, "geometry": {"type": "Polygon", "coordinates": [NORTH_ANDAMAN_COAST]}},
            {"type": "Feature", "properties": {"name": "Great Nicobar", "kind": "coastline"}, "geometry": {"type": "Polygon", "coordinates": [GREAT_NICOBAR_COAST]}},
        ],
    }


def get_indian_eez_geojson() -> Dict:
    """Return official VLIZ MarineRegions Indian 200 NM EEZ GeoJSON (MRGID 8480)."""
    return _load_real_eez()


def get_shipping_lanes_geojson() -> Dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": lane["name"], "kind": "shipping_lane"},
                "geometry": {"type": "LineString", "coordinates": lane["coords"]},
            }
            for lane in SHIPPING_LANES
        ],
    }


def get_restricted_zones_geojson() -> Dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": z["name"], "zone_type": z["zone_type"], "kind": "restricted_zone"},
                "geometry": {"type": "Polygon", "coordinates": [z["coords"]]},
            }
            for z in RESTRICTED_ZONES
        ],
    }


def get_critical_infrastructure_geojson() -> Dict:
    """Return real GFW Nature 2024 SAR-detected offshore structures in India's EEZ + major ports."""
    features = []
    for item in _load_real_infra():
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": f"GFW SAR Infra #{item.get('id')} ({item.get('label', 'offshore')})",
                    "infra_type": f"GFW Nature 2024 SAR Detection: {item.get('label', 'unknown')}",
                    "kind": "critical_infra",
                },
                "geometry": {"type": "Point", "coordinates": [float(item["lon"]), float(item["lat"])]},
            }
        )
    for port in MAJOR_INDIAN_PORTS:
        features.append(
            {
                "type": "Feature",
                "properties": {"name": port["name"], "infra_type": port["infra_type"], "kind": "critical_infra"},
                "geometry": {"type": "Point", "coordinates": [port["lon"], port["lat"]]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def nearest_shipping_lane_km(lat: float, lon: float) -> float:
    best = 999.0
    for lane in SHIPPING_LANES:
        coords = lane["coords"]
        for idx in range(len(coords) - 1):
            lon1, lat1 = coords[idx]
            lon2, lat2 = coords[idx + 1]
            d = _point_to_segment_km(lat, lon, lat1, lon1, lat2, lon2)
            if d < best:
                best = d
    return round(best, 2)


def nearest_offshore_infra_km(lat: float, lon: float) -> Tuple[float, str]:
    """Return distance in km to nearest real GFW-detected offshore structure."""
    infra = _load_real_infra()
    if not infra:
        return 999.0, ""
    best_d = 999.0
    best_lbl = ""
    for item in infra:
        d = haversine_km(lat, lon, float(item["lat"]), float(item["lon"]))
        if d < best_d:
            best_d = d
            best_lbl = f"GFW SAR {item.get('label', 'platform')} (#{item.get('id')})"
    return round(best_d, 2), best_lbl


def check_restricted_zone(lat: float, lon: float) -> Tuple[bool, str]:
    for zone in RESTRICTED_ZONES:
        if _point_in_polygon(lat, lon, zone["coords"]):
            return True, zone["name"]
    return False, ""


def estimate_eez_distance_nm(lat: float, lon: float) -> float:
    """Compute minimum distance in NM to the real MarineRegions Indian EEZ boundary."""
    _load_real_eez()
    if _EEZ_POINTS_RAD.size == 0:
        return 0.0
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    dlat = _EEZ_POINTS_RAD[:, 0] - lat_r
    dlon = _EEZ_POINTS_RAD[:, 1] - lon_r
    a = np.sin(dlat / 2.0) ** 2 + math.cos(lat_r) * np.cos(_EEZ_POINTS_RAD[:, 0]) * np.sin(dlon / 2.0) ** 2
    dists_km = 2.0 * EARTH_RADIUS_KM * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(0.0, 1.0 - a)))
    return round(float(np.min(dists_km)) * NM_PER_KM, 1)
