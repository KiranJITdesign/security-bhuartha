"""Database models for BhuArtha Sovereign Maritime Domain Awareness."""

from django.db import models


class SatellitePass(models.Model):
    """Stores SAR satellite pass metadata, swath geometry, and raw sensor feeds."""

    satellite_name = models.CharField(max_length=100)
    norad_id = models.IntegerField(default=39634)
    sector_code = models.CharField(max_length=64, unique=True)
    sector_name = models.CharField(max_length=180)
    pass_timestamp = models.DateTimeField()
    swath_geojson = models.JSONField(default=dict)
    center_lat = models.FloatField(default=18.9)
    center_lon = models.FloatField(default=71.2)
    default_zoom = models.IntegerField(default=7)
    orbit_altitude_km = models.FloatField(default=693.0)
    swath_width_km = models.FloatField(default=250.0)
    incidence_angle_deg = models.FloatField(default=34.5)
    raw_sar_contacts = models.JSONField(default=list)
    raw_ais_pings = models.JSONField(default=list)
    asf_scene_id = models.CharField(max_length=160, blank=True, default="")
    data_source = models.CharField(max_length=64, default="OPEN_API_HYBRID")
    last_scanned_at = models.DateTimeField(null=True, blank=True)
    scan_metrics = models.JSONField(default=dict)

    class Meta:
        db_table = "satellite_passes"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.satellite_name} | {self.sector_name}"


class VesselDetection(models.Model):
    """Stores fused SAR + AIS vessel classifications and AI anomaly scores."""

    RISK_CHOICES = [
        ("HIGH", "HIGH"),
        ("MEDIUM", "MEDIUM"),
        ("LOW", "LOW"),
    ]

    pass_ref = models.ForeignKey(
        SatellitePass,
        on_delete=models.CASCADE,
        related_name="detections",
        db_column="pass_id",
    )
    target_code = models.CharField(max_length=32)
    vessel_name = models.CharField(max_length=120, default="UNIDENTIFIED SAR TARGET")
    vessel_type = models.CharField(max_length=64, default="Unknown Contact")
    latitude = models.FloatField()
    longitude = models.FloatField()
    has_ais = models.BooleanField(default=False)
    ais_mmsi = models.CharField(max_length=32, null=True, blank=True)
    hull_length_m = models.FloatField()
    hull_width_m = models.FloatField(default=9.0)
    radar_cross_section_dbsm = models.FloatField(default=18.5)
    speed_knots = models.FloatField(default=0.0)
    heading_deg = models.FloatField(default=0.0)
    nearest_ais_distance_km = models.FloatField(default=0.0)
    eez_distance_nm = models.FloatField(default=0.0)
    nearest_lane_distance_km = models.FloatField(default=0.0)
    in_restricted_zone = models.BooleanField(default=False)
    restricted_zone_name = models.CharField(max_length=120, blank=True, default="")
    navic_gnss_anomaly = models.BooleanField(default=False)
    navic_status_note = models.CharField(max_length=180, blank=True, default="NavIC L5/S Timing Nominal")
    cfar_snr_db = models.FloatField(default=16.5)
    ai_confidence = models.FloatField(default=92.0)
    anomaly_score = models.FloatField(default=0.0)
    is_dark_vessel = models.BooleanField(default=False)
    risk_level = models.CharField(max_length=16, choices=RISK_CHOICES, default="LOW")
    risk_reasons = models.JSONField(default=list)
    sar_chip_seed = models.IntegerField(default=101)

    class Meta:
        db_table = "vessel_detections"
        ordering = ["-is_dark_vessel", "-anomaly_score", "id"]

    def __str__(self) -> str:
        status = "DARK" if self.is_dark_vessel else "AIS-VERIFIED"
        return f"{self.target_code} [{status} - {self.risk_level}]"


class EvidenceReport(models.Model):
    """Stores tamper-evident legal evidence packets for Indian Coast Guard / IFC-IOR."""

    STATUS_CHOICES = [
        ("GENERATED", "GENERATED"),
        ("DISPATCHED", "DISPATCHED"),
    ]

    detection = models.ForeignKey(
        VesselDetection,
        on_delete=models.CASCADE,
        related_name="evidence_reports",
        db_column="detection_id",
    )
    report_code = models.CharField(max_length=48, unique=True)
    officer_notes = models.TextField(blank=True, default="")
    evidence_hash = models.CharField(max_length=64)
    snapshot_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="GENERATED")

    class Meta:
        db_table = "evidence_reports"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.report_code} ({self.status})"
