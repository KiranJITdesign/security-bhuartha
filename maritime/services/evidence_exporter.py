"""Standalone printable HTML evidence packet generator for BhuArtha."""

from datetime import datetime, timedelta, timezone
import html
from maritime.models import EvidenceReport

IST_TZ = timezone(timedelta(hours=5, minutes=30))
COMPLIANCE_FOOTER = (
    "Track C Protective-Use Compliant: Monitoring, Early Warning & Evidence Generation Only. "
    "No weapons/targeting capabilities and no individual person tracking."
)


def _fmt_utc_ist(iso_str: str) -> str:
    if not iso_str:
        return "--"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        utc_s = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        ist_s = dt.astimezone(IST_TZ).strftime("%Y-%m-%d %H:%M:%S IST")
        return f"{utc_s} | {ist_s}"
    except Exception:
        return html.escape(iso_str)


def render_standalone_evidence_html(report: EvidenceReport, chip_data_uri: str) -> str:
    """Build a self-contained printable HTML Coast Guard evidence report."""
    snap = report.snapshot_payload or {}
    t = snap.get("target", {})
    s = snap.get("satellite", {})

    report_code = html.escape(report.report_code)
    status = html.escape(report.status)
    sector = html.escape(str(s.get("sector", report.detection.pass_ref.sector_name)))
    sat_name = html.escape(str(s.get("name", report.detection.pass_ref.satellite_name)))
    norad_id = html.escape(str(s.get("norad_id", report.detection.pass_ref.norad_id)))
    target_code = html.escape(str(t.get("target_code", report.detection.target_code)))
    vessel_name = html.escape(str(t.get("vessel_name", report.detection.vessel_name)))
    lat = float(t.get("latitude", report.detection.latitude))
    lon = float(t.get("longitude", report.detection.longitude))
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    coords_str = f"{abs(lat):.4f}° {ns}, {abs(lon):.4f}° {ew}"

    is_dark = bool(t.get("is_dark_vessel", report.detection.is_dark_vessel))
    ais_status = (
        f"AIS VERIFIED (MMSI {html.escape(str(t.get('ais_mmsi') or ''))})"
        if not is_dark
        else "DARK — NO TRANSPONDER PING"
    )
    risk_tier = html.escape(str(t.get("risk_level", report.detection.risk_level)))
    conf_pct = float(t.get("ai_confidence", report.detection.ai_confidence))
    hull_len = float(t.get("hull_length_m", report.detection.hull_length_m))
    hull_wid = float(t.get("hull_width_m", report.detection.hull_width_m))
    rcs = float(t.get("radar_cross_section_dbsm", report.detection.radar_cross_section_dbsm))
    snr = float(t.get("cfar_snr_db", report.detection.cfar_snr_db))
    eez_nm = float(t.get("eez_distance_nm", report.detection.eez_distance_nm))
    lane_km = float(t.get("nearest_lane_distance_km", report.detection.nearest_lane_distance_km))

    gen_ts = _fmt_utc_ist(snap.get("generated_at_utc") or report.created_at.isoformat())
    pass_ts = _fmt_utc_ist(str(s.get("pass_timestamp", "")))
    notes = html.escape(report.officer_notes or "Automated SAR-AIS anomaly logged for ICG patrol verification.")
    digest = html.escape(report.evidence_hash)

    reasons = t.get("risk_reasons") or []
    reasons_html = "".join(f"<li>{html.escape(str(r))}</li>" for r in reasons)

    risk_bg = "#FEE2E2" if risk_tier == "HIGH" else ("#FEF3C7" if risk_tier == "MEDIUM" else "#D1FAE5")
    risk_fg = "#991B1B" if risk_tier == "HIGH" else ("#92400E" if risk_tier == "MEDIUM" else "#065F46")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>BhuArtha Evidence Packet — {report_code}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background: #0B1120;
      color: #0F172A;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      line-height: 1.5;
    }}
    .toolbar {{
      max-width: 920px;
      margin: 0 auto 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #E2E8F0;
    }}
    .print-btn {{
      background: #06B6D4;
      color: #082F49;
      border: none;
      border-radius: 6px;
      padding: 9px 16px;
      font-weight: 700;
      cursor: pointer;
    }}
    .sheet {{
      max-width: 920px;
      margin: 0 auto;
      background: #FFFFFF;
      border-radius: 10px;
      padding: 28px 32px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.45);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0F172A;
      padding-bottom: 14px;
      margin-bottom: 18px;
      gap: 16px;
    }}
    .org {{ font-size: 20px; font-weight: 800; letter-spacing: 0.05em; color: #0F172A; }}
    .sub {{ font-size: 12px; color: #475569; font-weight: 600; margin-top: 2px; }}
    .case-box {{ text-align: right; font-family: monospace; }}
    .case-id {{ font-size: 14px; font-weight: 700; }}
    .badge {{
      display: inline-block;
      margin-top: 4px;
      padding: 3px 9px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      background: {risk_bg};
      color: {risk_fg};
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.35fr 1fr;
      gap: 22px;
      margin-bottom: 18px;
    }}
    h2 {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #0369A1;
      margin: 0 0 8px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 6px 8px; border-bottom: 1px solid #E2E8F0; text-align: left; }}
    th {{ width: 38%; color: #475569; font-weight: 600; }}
    td {{ font-family: monospace; color: #0F172A; }}
    .chip-wrap img {{
      width: 100%;
      max-width: 300px;
      border: 1px solid #94A3B8;
      border-radius: 6px;
      display: block;
    }}
    .notes-box {{
      margin-top: 10px;
      background: #F8FAFC;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      padding: 10px 12px;
    }}
    .reasons {{
      background: #FEF2F2;
      border: 1px solid #FECACA;
      border-radius: 6px;
      padding: 12px 16px;
      margin-bottom: 14px;
    }}
    .reasons ul {{ margin: 6px 0 0; padding-left: 18px; }}
    .hash-bar {{
      background: #F1F5F9;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      padding: 9px 12px;
      font-family: monospace;
      font-size: 11px;
      word-break: break-all;
      margin-bottom: 16px;
    }}
    .footer {{
      border-top: 1px solid #CBD5E1;
      padding-top: 10px;
      font-size: 11px;
      font-weight: 600;
      color: #065F46;
      text-align: center;
    }}
    @media print {{
      body {{ background: #FFFFFF; padding: 0; }}
      .toolbar {{ display: none !important; }}
      .sheet {{ box-shadow: none; padding: 12px; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar">
    <span>BhuArtha Official Maritime Evidence Export ({report_code})</span>
    <button class="print-btn" type="button" onclick="window.print()">Print / Save as PDF</button>
  </div>
  <main class="sheet">
    <div class="header">
      <div>
        <div class="org">BhuArtha — Sovereign Maritime Domain Awareness</div>
        <div class="sub">Indian Coast Guard &amp; IFC-IOR Protective Enforcement Evidence Brief | Track C</div>
      </div>
      <div class="case-box">
        <div class="case-id">CASE ID: {report_code}</div>
        <div class="badge">RISK: {risk_tier} | STATUS: {status}</div>
      </div>
    </div>

    <div class="grid">
      <div>
        <h2>Target &amp; Orbital Pass Telemetry</h2>
        <table>
          <tr><th>Target Code / Label</th><td>{target_code} ({vessel_name})</td></tr>
          <tr><th>AIS Transponder Status</th><td><strong>{ais_status}</strong></td></tr>
          <tr><th>AI Confidence / Risk</th><td>{conf_pct:.1f}% | {risk_tier} TIER</td></tr>
          <tr><th>Coordinates (WGS84)</th><td>{coords_str}</td></tr>
          <tr><th>Maritime Sector</th><td>{sector}</td></tr>
          <tr><th>Timestamp (UTC | IST)</th><td>{gen_ts}</td></tr>
          <tr><th>Satellite Pass</th><td>{sat_name} (NORAD {norad_id}) @ {pass_ts}</td></tr>
          <tr><th>SAR Hull / RCS / SNR</th><td>{hull_len:.0f}m × {hull_wid:.1f}m | {rcs:.1f} dBsm | {snr:.1f} dB</td></tr>
          <tr><th>EEZ / Shipping Lane</th><td>{eez_nm:.1f} NM from outer EEZ | {lane_km:.1f} km off lane</td></tr>
          <tr><th>Legal Basis</th><td>UNCLOS Part V &amp; Maritime Zones of India Act, 1976</td></tr>
        </table>
      </div>
      <div class="chip-wrap">
        <h2>2D CA-CFAR SAR Radar Chip</h2>
        <img src="{chip_data_uri}" alt="2D CA-CFAR radar chip showing isolated metallic hull bounding box" />
        <div class="notes-box">
          <strong>Duty Officer Observations:</strong>
          <div>{notes}</div>
        </div>
      </div>
    </div>

    <div class="reasons">
      <strong>Automated SAR-AIS Fusion &amp; IsolationForest Findings:</strong>
      <ul>{reasons_html}</ul>
    </div>

    <div class="hash-bar">
      <strong>SHA-256 TAMPER-EVIDENT DIGEST:</strong> {digest}
    </div>

    <footer class="footer">{COMPLIANCE_FOOTER}</footer>
  </main>
</body>
</html>
"""
