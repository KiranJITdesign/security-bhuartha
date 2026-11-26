"""Admin registration for BhuArtha Sovereign Maritime Domain Awareness."""

from django.contrib import admin
from .models import EvidenceReport, SatellitePass, VesselDetection

admin.site.site_header = "BhuArtha Command Administration"
admin.site.site_title = "BhuArtha MDA Admin"
admin.site.index_title = "Sovereign Maritime Domain Awareness | Track C"


@admin.register(SatellitePass)
class SatellitePassAdmin(admin.ModelAdmin):
    list_display = ("id", "satellite_name", "sector_name", "pass_timestamp", "data_source", "last_scanned_at")
    search_fields = ("satellite_name", "sector_name", "sector_code")


@admin.register(VesselDetection)
class VesselDetectionAdmin(admin.ModelAdmin):
    list_display = ("target_code", "pass_ref", "is_dark_vessel", "risk_level", "ai_confidence", "has_ais", "ais_mmsi")
    list_filter = ("is_dark_vessel", "risk_level", "navic_gnss_anomaly")
    search_fields = ("target_code", "vessel_name", "ais_mmsi")


@admin.register(EvidenceReport)
class EvidenceReportAdmin(admin.ModelAdmin):
    list_display = ("report_code", "detection", "status", "created_at", "dispatched_at")
    list_filter = ("status",)
    search_fields = ("report_code", "evidence_hash")
