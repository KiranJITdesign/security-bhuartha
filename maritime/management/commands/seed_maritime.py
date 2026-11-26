"""Idempotent management command to seed BhuArtha purely from extracted real GFW + ASF Sentinel-1 datasets."""

from datetime import datetime, timezone
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from maritime.models import SatellitePass, VesselDetection
from maritime.services.cfar_detector import prebuild_cached_chips
from maritime.services.fusion_engine import run_sar_ais_fusion_scan

REAL_SCENES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "india_real_scenes.json"

SECTOR_LABELS = {
    "arabian_sea_s4": "Arabian Sea — Mumbai & Konkan Coast",
    "kerala_lakshadweep": "SW Coast — Mangaluru & Lakshadweep Sea",
    "bay_of_bengal_odisha": "Northern Bay of Bengal — Haldia & Sundarbans Approach",
    "andaman_nicobar": "Great Nicobar — Six Degree Malacca Chokepoint",
}


def seed_all_sectors(fetch_live_asf: bool = True) -> int:
    """Load real Global Fishing Watch Nature 2024 + ASF Sentinel-1 scenes and run fusion."""
    if not REAL_SCENES_PATH.exists():
        raise FileNotFoundError(f"Real dataset file missing: {REAL_SCENES_PATH}")

    scenes = json.loads(REAL_SCENES_PATH.read_text(encoding="utf-8"))
    created_or_updated = 0

    for s_idx, scene in enumerate(scenes, start=1):
        scene_id = scene["scene_id"]
        sat_name = "Sentinel-1B" if scene_id.startswith("S1B_") else "Sentinel-1A"
        norad_id = 41456 if sat_name == "Sentinel-1B" else 39634

        ts_raw = scene["timestamp"].replace(" ", "T")
        if ts_raw.endswith("+00:00"):
            pass_ts = datetime.fromisoformat(ts_raw)
        else:
            pass_ts = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)

        raw_sar_contacts = []
        raw_ais_pings = []
        for idx, rec in enumerate(scene["records"], start=1):
            prefix = "BA-DARK" if rec["is_dark"] else "BA-SAR"
            code = f"{prefix}-{s_idx:02d}{idx:02d}"
            raw_sar_contacts.append(
                {
                    "target_code": code,
                    "lat": float(rec["lat"]),
                    "lon": float(rec["lon"]),
                    "hull_length_m": float(rec["length_m"]) if rec.get("length_m") else 24.0,
                    "fishing_score": float(rec["fishing_score"]) if rec.get("fishing_score") is not None else 0.5,
                    "matching_score": float(rec["matching_score"]) if rec.get("matching_score") is not None else 0.0,
                    "matched_category": rec.get("matched_category", "unmatched"),
                    "overpasses_2017_2021": rec.get("overpasses_2017_2021", 0),
                    "chip_seed": s_idx * 1000 + idx,
                }
            )
            if not rec["is_dark"] and rec.get("mmsi"):
                raw_ais_pings.append(
                    {
                        "mmsi": str(rec["mmsi"]),
                        "lat": float(rec["lat"]),
                        "lon": float(rec["lon"]),
                        "matching_score": float(rec["matching_score"]) if rec.get("matching_score") is not None else 0.0,
                    }
                )

        sector_code = scene["sector_code"]
        sat_pass, _ = SatellitePass.objects.update_or_create(
            sector_code=sector_code,
            defaults={
                "satellite_name": sat_name,
                "norad_id": norad_id,
                "sector_name": SECTOR_LABELS.get(sector_code, scene["sector_name"]),
                "pass_timestamp": pass_ts,
                "swath_geojson": scene["swath_geojson"],
                "center_lat": float(scene["center_lat"]),
                "center_lon": float(scene["center_lon"]),
                "default_zoom": 8,
                "orbit_altitude_km": 693.0,
                "swath_width_km": 250.0,
                "incidence_angle_deg": 36.2,
                "raw_sar_contacts": raw_sar_contacts,
                "raw_ais_pings": raw_ais_pings,
                "asf_scene_id": scene_id,
                "data_source": "GFW_NATURE2024_ASF_S1",
                "scan_metrics": {"local_browse_path": scene.get("local_browse_path", "")},
            },
        )
        run_sar_ais_fusion_scan(sat_pass)
        created_or_updated += 1

    prebuild_cached_chips(list(VesselDetection.objects.select_related("pass_ref").all()))
    return created_or_updated


class Command(BaseCommand):
    help = "Seed BhuArtha purely from real extracted Global Fishing Watch + ASF Sentinel-1 Indian Ocean datasets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Accepted for compatibility; real datasets are already extracted locally.",
        )

    def handle(self, *args, **options):
        count = seed_all_sectors()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {count} real Sentinel-1 passes ({VesselDetection.objects.count()} real vessel detections) & rebuilt SAR chip cache."
            )
        )
