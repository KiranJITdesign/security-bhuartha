"""URL routing for BhuArtha maritime command dashboard and REST API."""

from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/passes/", views.api_passes, name="api_passes"),
    path("api/scan/<int:pass_id>/", views.api_scan_pass, name="api_scan_pass"),
    path("api/vessel/<int:vessel_id>/", views.api_vessel_detail, name="api_vessel_detail"),
    path("api/evidence/<int:vessel_id>/", views.api_generate_evidence, name="api_generate_evidence"),
    path("api/evidence/", views.api_evidence_list_or_dispatch, name="api_evidence_list"),
    path("api/evidence/<int:report_id>/dispatch/", views.api_evidence_list_or_dispatch, name="api_evidence_dispatch"),
    path("api/evidence/<int:report_id>/export/", views.api_export_evidence, name="api_evidence_export"),
    path("api/orbital-live/", views.api_orbital_live, name="api_orbital_live"),
]
