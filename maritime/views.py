"""REST API views & dashboard view for BhuArtha Sovereign Maritime Domain Awareness."""

import json
from datetime import datetime, timezone
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from maritime.models import EvidenceReport, SatellitePass, VesselDetection
from maritime.services.cfar_detector import generate_sar_chip_bundle
from maritime.services.evidence_exporter import render_standalone_evidence_html
from maritime.services.fusion_engine import create_evidence_packet, run_sar_ais_fusion_scan
from maritime.services.maritime_layers import (
    get_critical_infrastructure_geojson,
    get_indian_coastline_geojson,
    get_indian_eez_geojson,
    get_restricted_zones_geojson,
    get_shipping_lanes_geojson,
)
from maritime.services.orbital_physics import (
    compute_physics_and_economics,
    get_live_constellation_telemetry,
)


def _human_size_label(length_m: float) -> str:
    if length_m < 20.0:
        return f"{length_m:.1f} m (Small Boat / Trawler)"
    if length_m < 50.0:
        return f"{length_m:.1f} m (Medium Vessel)"
    return f"{length_m:.1f} m (Large Ship)"


def _human_summary(d: VesselDetection) -> str:
    if d.is_dark_vessel:
        loc_note = (
            f"inside {d.restricted_zone_name}"
            if d.in_restricted_zone and d.restricted_zone_name
            else f"{d.eez_distance_nm:.1f} NM from the outer EEZ edge"
        )
        return (
            f"Alert: Satellite radar spotted an unidentified {d.hull_length_m:.1f} m vessel "
            f"({d.vessel_type.lower()}) {loc_note}, with its AIS tracking beacon switched OFF. "
            f"The nearest legal broadcasting ship is {d.nearest_ais_distance_km:.1f} km away."
        )
    return (
        f"Verified Legal Ship: This {d.hull_length_m:.1f} m vessel ({d.vessel_type}) "
        f"is broadcasting a valid AIS signal (MMSI {d.ais_mmsi}) matching the satellite radar return."
    )


def _serialize_detection(d: VesselDetection) -> dict:
    """Serialize VesselDetection record cleanly for map and sidebar rendering."""
    latest_report = d.evidence_reports.first()
    return {
        "id": d.id,
        "pass_id": d.pass_ref_id,
        "target_code": d.target_code,
        "vessel_name": d.vessel_name,
        "vessel_type": d.vessel_type,
        "human_size": _human_size_label(d.hull_length_m),
        "human_summary": _human_summary(d),
        "latitude": d.latitude,
        "longitude": d.longitude,
        "has_ais": d.has_ais,
        "ais_mmsi": d.ais_mmsi,
        "ais_status_label": (
            f"AIS VERIFIED (MMSI {d.ais_mmsi})"
            if d.has_ais
            else "DARK — NO TRANSPONDER PING"
        ),
        "hull_length_m": d.hull_length_m,
        "hull_width_m": d.hull_width_m,
        "radar_cross_section_dbsm": d.radar_cross_section_dbsm,
        "speed_knots": d.speed_knots,
        "heading_deg": d.heading_deg,
        "nearest_ais_distance_km": d.nearest_ais_distance_km,
        "eez_distance_nm": d.eez_distance_nm,
        "nearest_lane_distance_km": d.nearest_lane_distance_km,
        "in_restricted_zone": d.in_restricted_zone,
        "restricted_zone_name": d.restricted_zone_name,
        "navic_gnss_anomaly": d.navic_gnss_anomaly,
        "navic_status_note": d.navic_status_note,
        "cfar_snr_db": d.cfar_snr_db,
        "ai_confidence": d.ai_confidence,
        "anomaly_score": d.anomaly_score,
        "is_dark_vessel": d.is_dark_vessel,
        "risk_level": d.risk_level,
        "risk_reasons": d.risk_reasons,
        "latest_report_code": latest_report.report_code if latest_report else None,
        "latest_report_status": latest_report.status if latest_report else None,
    }


def _serialize_report(r: EvidenceReport) -> dict:
    """Serialize EvidenceReport for modal, audit feed & export links."""
    return {
        "id": r.id,
        "platform": "BhuArtha",
        "detection_id": r.detection_id,
        "target_code": r.detection.target_code,
        "vessel_name": r.detection.vessel_name,
        "sector_name": r.detection.pass_ref.sector_name,
        "report_code": r.report_code,
        "officer_notes": r.officer_notes,
        "evidence_hash": r.evidence_hash,
        "snapshot_payload": r.snapshot_payload,
        "created_at": r.created_at.isoformat(),
        "dispatched_at": r.dispatched_at.isoformat() if r.dispatched_at else None,
        "status": r.status,
        "export_html_url": f"/api/evidence/{r.id}/export/?format=html",
        "export_json_url": f"/api/evidence/{r.id}/export/?format=json",
    }


def _chip_for_detection(detection: VesselDetection) -> dict:
    sat_pass = detection.pass_ref
    metrics = sat_pass.scan_metrics or {}
    return generate_sar_chip_bundle(
        hull_length_m=detection.hull_length_m,
        hull_width_m=detection.hull_width_m,
        rcs_dbsm=detection.radar_cross_section_dbsm,
        heading_deg=detection.heading_deg,
        seed=detection.sar_chip_seed,
        is_dark=detection.is_dark_vessel,
        browse_rel_path=metrics.get("local_browse_path", ""),
        swath_geojson=sat_pass.swath_geojson,
        lat=detection.latitude,
        lon=detection.longitude,
        scene_id=sat_pass.asf_scene_id,
    )


def dashboard(request):
    """Render the single-page BhuArtha Maritime Command Center."""
    return render(
        request,
        "maritime/dashboard.html",
        {
            "db_mode": getattr(settings, "ACTIVE_DB_MODE", "LOCAL_FALLBACK"),
            "db_label": getattr(settings, "ACTIVE_DB_LABEL", "DB: LOCAL FALLBACK"),
        },
    )


def _serialize_pass(p: SatellitePass) -> dict:
    """Serialize SatellitePass with full orbital & sensor metadata for the left info panel."""
    return {
        "id": p.id,
        "satellite_name": p.satellite_name,
        "norad_id": p.norad_id,
        "sector_code": p.sector_code,
        "sector_name": p.sector_name,
        "pass_timestamp": p.pass_timestamp.isoformat(),
        "swath_geojson": p.swath_geojson,
        "center_lat": p.center_lat,
        "center_lon": p.center_lon,
        "default_zoom": p.default_zoom,
        "orbit_altitude_km": p.orbit_altitude_km,
        "orbital_velocity_km_s": 7.51,
        "orbital_period_min": 98.6,
        "inclination_deg": 98.18,
        "radar_band": "C-Band Dual-Pol SAR (5.405 GHz)",
        "swath_width_km": p.swath_width_km,
        "incidence_angle_deg": p.incidence_angle_deg,
        "asf_scene_id": p.asf_scene_id,
        "data_source": p.data_source,
        "last_scanned_at": p.last_scanned_at.isoformat() if p.last_scanned_at else None,
        "scan_metrics": p.scan_metrics,
    }


@require_GET
def api_passes(request):
    """GET /api/passes/ — Fetch satellite sectors, pass metadata, GIS layers & live orbits."""
    passes = list(SatellitePass.objects.all())
    pass_items = [_serialize_pass(p) for p in passes]

    constellation = get_live_constellation_telemetry()
    return JsonResponse(
        {
            "platform": "BhuArtha",
            "subtitle": "Sovereign Maritime Domain Awareness | Track C",
            "database": {
                "mode": getattr(settings, "ACTIVE_DB_MODE", "LOCAL_FALLBACK"),
                "label": getattr(settings, "ACTIVE_DB_LABEL", "DB: LOCAL FALLBACK"),
            },
            "passes": pass_items,
            "constellation": constellation,
            "layers": {
                "coastline": get_indian_coastline_geojson(),
                "eez_boundary": get_indian_eez_geojson(),
                "shipping_lanes": get_shipping_lanes_geojson(),
                "restricted_zones": get_restricted_zones_geojson(),
                "critical_infrastructure": get_critical_infrastructure_geojson(),
            },
            "physics_economics": compute_physics_and_economics(),
        }
    )


@csrf_exempt
@require_http_methods(["POST", "GET"])
def api_scan_pass(request, pass_id: int):
    """POST /api/scan/<pass_id>/ — Execute SAR-vs-AIS fusion & ML scoring, return vessels + KPIs."""
    sat_pass = get_object_or_404(SatellitePass, pk=pass_id)
    result = run_sar_ais_fusion_scan(sat_pass)
    kpis = result["kpis"]
    physics_econ = compute_physics_and_economics(
        dark_count=kpis.get("dark_vessels_flagged", 0),
        total_scanned=kpis.get("total_scanned", 0),
    )

    risk_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ordered_vessels = sorted(
        result["detections"],
        key=lambda d: (0 if d.is_dark_vessel else 1, risk_rank.get(d.risk_level, 3), -d.anomaly_score, d.id),
    )

    return JsonResponse(
        {
            "platform": "BhuArtha",
            "pass": _serialize_pass(sat_pass),
            "kpis": kpis,
            "physics_economics": physics_econ,
            "vessels": [_serialize_detection(d) for d in ordered_vessels],
        }
    )


@require_GET
def api_vessel_detail(request, vessel_id: int):
    """GET /api/vessel/<id>/ — Return full telemetry, risk breakdown & cached/live SAR CFAR chip."""
    detection = get_object_or_404(VesselDetection.objects.select_related("pass_ref"), pk=vessel_id)
    chip_bundle = _chip_for_detection(detection)
    payload = _serialize_detection(detection)
    payload["platform"] = "BhuArtha"
    payload["satellite_name"] = detection.pass_ref.satellite_name
    payload["sector_name"] = detection.pass_ref.sector_name
    payload["pass_timestamp"] = detection.pass_ref.pass_timestamp.isoformat()
    payload["incidence_angle_deg"] = detection.pass_ref.incidence_angle_deg
    payload["asf_scene_id"] = detection.pass_ref.asf_scene_id
    payload["sar_chip"] = chip_bundle
    payload["evidence_reports"] = [_serialize_report(r) for r in detection.evidence_reports.all()[:5]]
    return JsonResponse({"platform": "BhuArtha", "vessel": payload})


@csrf_exempt
@require_http_methods(["POST"])
def api_generate_evidence(request, vessel_id: int):
    """POST /api/evidence/<vessel_id>/ — Save tamper-evident legal evidence packet in DB."""
    detection = get_object_or_404(VesselDetection.objects.select_related("pass_ref"), pk=vessel_id)
    officer_notes = ""
    auto_dispatch = False
    if request.body:
        try:
            body = json.loads(request.body.decode("utf-8"))
            officer_notes = str(body.get("officer_notes", ""))
            auto_dispatch = bool(body.get("dispatch", False))
        except Exception:
            pass

    report = create_evidence_packet(detection, officer_notes=officer_notes)
    if auto_dispatch:
        report.status = "DISPATCHED"
        report.dispatched_at = datetime.now(timezone.utc)
        report.save(update_fields=["status", "dispatched_at"])

    chip_bundle = _chip_for_detection(detection)
    data = _serialize_report(report)
    data["sar_chip_data_uri"] = chip_bundle["chip_data_uri"]
    return JsonResponse({"platform": "BhuArtha", "report": data}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_evidence_list_or_dispatch(request, report_id: int = None):
    """GET /api/evidence/ or POST /api/evidence/<report_id>/dispatch/."""
    if report_id is not None and request.method == "POST":
        report = get_object_or_404(
            EvidenceReport.objects.select_related("detection", "detection__pass_ref"),
            pk=report_id,
        )
        if report.status != "DISPATCHED":
            report.status = "DISPATCHED"
            report.dispatched_at = datetime.now(timezone.utc)
            report.save(update_fields=["status", "dispatched_at"])
        return JsonResponse({"platform": "BhuArtha", "report": _serialize_report(report)})

    reports = EvidenceReport.objects.select_related("detection", "detection__pass_ref").all()[:30]
    return JsonResponse({"platform": "BhuArtha", "reports": [_serialize_report(r) for r in reports]})


@require_GET
def api_export_evidence(request, report_id: int):
    """GET /api/evidence/<report_id>/export/?format=html|json — Downloadable standalone report."""
    report = get_object_or_404(
        EvidenceReport.objects.select_related("detection", "detection__pass_ref"),
        pk=report_id,
    )
    fmt = request.GET.get("format", "html").lower()
    if fmt == "json":
        payload = json.dumps(report.snapshot_payload, indent=2)
        resp = HttpResponse(payload, content_type="application/json; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="BhuArtha-Evidence-{report.report_code}.json"'
        return resp

    chip_bundle = _chip_for_detection(report.detection)
    html_doc = render_standalone_evidence_html(report, chip_bundle["chip_data_uri"])
    resp = HttpResponse(html_doc, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="BhuArtha-Evidence-{report.report_code}.html"'
    return resp


@require_GET
def api_orbital_live(request):
    """GET /api/orbital-live/ — Return live/cached CelesTrak orbital propagation state."""
    return JsonResponse({"platform": "BhuArtha", "constellation": get_live_constellation_telemetry()})
