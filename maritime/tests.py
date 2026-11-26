"""Automated test suite for BhuArtha real GFW + ASF + MarineRegions data pipeline."""

import json
from django.test import Client, TestCase
from maritime.management.commands.seed_maritime import seed_all_sectors
from maritime.models import EvidenceReport, SatellitePass, VesselDetection
from maritime.services.cfar_detector import CHIP_CACHE_PATH, generate_sar_chip_bundle
from maritime.services.evidence_exporter import COMPLIANCE_FOOTER


class BhuArthaRealDataEndToEndTests(TestCase):
    """Verify real GFW/ASF/MarineRegions seeding, REST APIs, real SAR CFAR chips & exports."""

    @classmethod
    def setUpTestData(cls):
        seed_all_sectors()

    def setUp(self):
        self.client = Client()

    def test_seeded_real_gfw_passes_and_chip_cache(self):
        self.assertEqual(SatellitePass.objects.count(), 4)
        arabian = SatellitePass.objects.get(sector_code="arabian_sea_s4")
        self.assertEqual(arabian.detections.count(), 49)
        self.assertEqual(arabian.detections.filter(is_dark_vessel=True).count(), 35)
        self.assertEqual(arabian.detections.filter(has_ais=True).count(), 14)
        self.assertTrue(CHIP_CACHE_PATH.exists())

    def test_dashboard_rebrand_and_db_badge(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "BHUARTHA")
        self.assertContains(resp, "Sovereign Maritime Domain Awareness | Track C")
        self.assertContains(resp, "DB: LOCAL FALLBACK")
        self.assertContains(resp, "DATA: GFW+ASF+VLIZ REAL")
        self.assertContains(resp, "Tactical Dark")
        self.assertContains(resp, "Satellite")
        self.assertContains(resp, "AREA &amp; SATELLITE INFO")
        self.assertContains(resp, "WHY THIS VESSEL WAS FLAGGED")
        self.assertNotContains(resp, 'id="sectorSelect"')
        self.assertNotContains(resp, "Sagar-Drishti")

    def test_api_passes_real_eez_and_gfw_infra(self):
        resp = self.client.get("/api/passes/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["platform"], "BhuArtha")
        self.assertEqual(data["database"]["mode"], "LOCAL_FALLBACK")
        self.assertEqual(len(data["passes"]), 4)
        self.assertTrue(len(data["layers"]["eez_boundary"]["features"]) >= 1)
        self.assertGreaterEqual(len(data["layers"]["critical_infrastructure"]["features"]), 300)
        sat_names = [s["satellite_name"] for s in data["constellation"]["satellites"]]
        self.assertIn("SENTINEL-1A", sat_names)
        self.assertIn("EOS-04 (RISAT-1A)", sat_names)
        self.assertIn("NISAR (ISRO-NASA)", sat_names)

    def test_api_scan_pass_fusion(self):
        arabian = SatellitePass.objects.get(sector_code="arabian_sea_s4")
        resp = self.client.post(f"/api/scan/{arabian.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["platform"], "BhuArtha")
        self.assertEqual(data["kpis"]["total_scanned"], 49)
        self.assertEqual(data["kpis"]["dark_vessels_flagged"], 35)
        self.assertEqual(data["kpis"]["legal_vessels"], 14)
        self.assertTrue(data["vessels"][0]["is_dark_vessel"])
        self.assertIn(data["vessels"][0]["risk_level"], ("HIGH", "MEDIUM", "LOW"))

    def test_api_vessel_detail_and_real_sar_chip(self):
        dark_vessel = VesselDetection.objects.filter(is_dark_vessel=True).first()
        resp = self.client.get(f"/api/vessel/{dark_vessel.id}/")
        self.assertEqual(resp.status_code, 200)
        v = resp.json()["vessel"]
        self.assertEqual(v["ais_status_label"], "DARK — NO TRANSPONDER PING")
        self.assertTrue(v["sar_chip"]["chip_data_uri"].startswith("data:image/png;base64,"))
        self.assertEqual(v["sar_chip"]["source_label"], "REAL SENTINEL-1 SAR")
        self.assertGreater(v["sar_chip"]["cfar_snr_db"], 0.0)

    def test_cfar_chip_direct_real_scene_crop(self):
        arabian = SatellitePass.objects.get(sector_code="arabian_sea_s4")
        dark_vessel = arabian.detections.filter(is_dark_vessel=True).first()
        bundle = generate_sar_chip_bundle(
            hull_length_m=dark_vessel.hull_length_m,
            hull_width_m=dark_vessel.hull_width_m,
            rcs_dbsm=dark_vessel.radar_cross_section_dbsm,
            heading_deg=dark_vessel.heading_deg,
            seed=dark_vessel.sar_chip_seed,
            is_dark=True,
            browse_rel_path=(arabian.scan_metrics or {}).get("local_browse_path", ""),
            swath_geojson=arabian.swath_geojson,
            lat=dark_vessel.latitude,
            lon=dark_vessel.longitude,
            scene_id=arabian.asf_scene_id,
        )
        self.assertEqual(bundle["source_label"], "REAL SENTINEL-1 SAR")
        self.assertGreater(bundle["cfar_pixels"], 0)

    def test_evidence_generation_dispatch_and_standalone_exports(self):
        dark_vessel = VesselDetection.objects.filter(is_dark_vessel=True).first()
        resp = self.client.post(
            f"/api/evidence/{dark_vessel.id}/",
            data=json.dumps({"officer_notes": "Real GFW dark target queued for ICG", "dispatch": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        report_data = resp.json()["report"]
        self.assertTrue(report_data["report_code"].startswith("BA-EVD-"))
        self.assertEqual(report_data["status"], "DISPATCHED")
        self.assertEqual(len(report_data["evidence_hash"]), 64)

        html_resp = self.client.get(f"/api/evidence/{report_data['id']}/export/?format=html")
        self.assertEqual(html_resp.status_code, 200)
        body = html_resp.content.decode("utf-8")
        self.assertIn("BhuArtha", body)
        self.assertIn("DARK — NO TRANSPONDER PING", body)
        self.assertIn("Print / Save as PDF", body)
        self.assertIn("data:image/png;base64,", body)
        self.assertIn(COMPLIANCE_FOOTER, body)

        json_resp = self.client.get(f"/api/evidence/{report_data['id']}/export/?format=json")
        self.assertEqual(json_resp.status_code, 200)
        exported_json = json.loads(json_resp.content.decode("utf-8"))
        self.assertEqual(exported_json["platform"], "BhuArtha")
        self.assertEqual(EvidenceReport.objects.filter(status="DISPATCHED").count(), 1)
