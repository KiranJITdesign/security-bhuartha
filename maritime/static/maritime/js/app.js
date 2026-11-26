/* BhuArtha Frontend Command Controller */
(() => {
  "use strict";

  const state = {
    passes: [],
    currentPassId: null,
    vessels: [],
    selectedVesselId: null,
    selectedVesselDetail: null,
    currentFilter: "ALL",
    activeReport: null,
    constellation: null,
    physicsEconomics: null,
    gisLayers: null,
    basemapStage: 0,
    mapViewMode: "dark",
  };

  let map = null;
  let activeBasemapLayers = [];
  let coastlineGeoJsonLayer = null;
  const layerGroups = {
    swath: null,
    ais: null,
    dark: null,
    eez: null,
    infra: null,
    orbit: null,
  };
  const markerByVesselId = new Map();

  const $ = (id) => document.getElementById(id);

  function showToast(msg, durationMs = 3400) {
    const el = $("toastBanner");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => el.classList.add("hidden"), durationMs);
  }

  function formatUtcShort(isoStr) {
    if (!isoStr) return "--";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return isoStr;
    return d.toISOString().replace("T", " ").slice(0, 16) + "Z";
  }

  function formatUtcAndIst(isoStr) {
    if (!isoStr) return "--";
    const d = new Date(isoStr);
    if (Number.isNaN(d.getTime())) return isoStr;
    const utc = d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
    const istDate = new Date(d.getTime() + 330 * 60000);
    const ist = istDate.toISOString().replace("T", " ").slice(0, 19) + " IST";
    return `${utc} | ${ist}`;
  }

  function formatLatLon(lat, lon) {
    const ns = lat >= 0 ? "N" : "S";
    const ew = lon >= 0 ? "E" : "W";
    return `${Math.abs(lat).toFixed(4)}° ${ns}, ${Math.abs(lon).toFixed(4)}° ${ew}`;
  }

  function updateCoastlineStyle() {
    if (!coastlineGeoJsonLayer) return;
    if (state.mapViewMode === "satellite") {
      coastlineGeoJsonLayer.setStyle({
        color: "#38BDF8",
        weight: 1.2,
        fillColor: "#1E293B",
        fillOpacity: 0.0,
        opacity: 0.45,
      });
    } else {
      coastlineGeoJsonLayer.setStyle({
        color: "#475569",
        weight: 1.4,
        fillColor: "#1E293B",
        fillOpacity: 0.25,
        opacity: 0.72,
      });
    }
  }

  function setBasemapStage(stageIndex, viewMode = state.mapViewMode) {
    activeBasemapLayers.forEach((lyr) => {
      if (map.hasLayer(lyr)) map.removeLayer(lyr);
    });
    activeBasemapLayers = [];
    state.basemapStage = stageIndex;
    state.mapViewMode = viewMode;
    updateCoastlineStyle();

    let errorCount = 0;
    const attachErrorFallback = (tileLayer, nextStage, nextMode = viewMode) => {
      tileLayer.on("tileerror", () => {
        errorCount += 1;
        if (errorCount === 4 && state.basemapStage === stageIndex && state.mapViewMode === viewMode) {
          setBasemapStage(nextStage, nextMode);
        }
      });
    };

    if (viewMode === "satellite") {
      const esriSat = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "Imagery &copy; Esri | BhuArtha MDA", maxZoom: 17 }
      );
      const esriLabels = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 17, opacity: 0.88 }
      );
      attachErrorFallback(esriSat, 0, "dark");
      esriSat.addTo(map);
      esriLabels.addTo(map);
      activeBasemapLayers = [esriSat, esriLabels];
      $("basemapActiveLabel").textContent = "Esri Satellite";
      return;
    }

    if (stageIndex === 0) {
      const esriBase = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        { attribution: "Tiles &copy; Esri | BhuArtha MDA", maxZoom: 16 }
      );
      const esriRef = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 16, opacity: 0.78 }
      );
      attachErrorFallback(esriBase, 1, "dark");
      esriBase.addTo(map);
      esriRef.addTo(map);
      activeBasemapLayers = [esriBase, esriRef];
      $("basemapActiveLabel").textContent = "Esri Dark Gray";
    } else if (stageIndex === 1) {
      const carto = L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        { attribution: "&copy; OpenStreetMap &copy; CARTO | BhuArtha MDA", subdomains: "abcd", maxZoom: 18 }
      );
      attachErrorFallback(carto, 2, "dark");
      carto.addTo(map);
      activeBasemapLayers = [carto];
      $("basemapActiveLabel").textContent = "CartoDB Dark";
    } else if (stageIndex === 2) {
      const osmDark = L.tileLayer(
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          attribution: "&copy; OpenStreetMap | BhuArtha MDA",
          maxZoom: 18,
          className: "dark-osm-tiles",
        }
      );
      attachErrorFallback(osmDark, 3, "dark");
      osmDark.addTo(map);
      activeBasemapLayers = [osmDark];
      $("basemapActiveLabel").textContent = "OSM Tactical Dark";
    } else {
      $("basemapActiveLabel").textContent = "Offline Vector GeoJSON";
      showToast("Offline mode: rendering bundled Indian Coastline & EEZ GeoJSON.");
    }
  }

  function initMap() {
    map = L.map("maritimeMap", {
      center: [18.5, 72.5],
      zoom: 6,
      zoomControl: false,
      attributionControl: true,
    });

    L.control.zoom({ position: "topright" }).addTo(map);
    L.control.scale({ position: "bottomleft", imperial: false }).addTo(map);

    setBasemapStage(0);

    layerGroups.eez = L.layerGroup().addTo(map);
    layerGroups.swath = L.layerGroup().addTo(map);
    layerGroups.infra = L.layerGroup().addTo(map);
    layerGroups.orbit = L.layerGroup().addTo(map);
    layerGroups.ais = L.layerGroup().addTo(map);
    layerGroups.dark = L.layerGroup().addTo(map);

    map.on("mousemove", (ev) => {
      const { lat, lng } = ev.latlng;
      const ns = lat >= 0 ? "N" : "S";
      const ew = lng >= 0 ? "E" : "W";
      $("hudCoords").textContent = `LAT ${Math.abs(lat).toFixed(4)}° ${ns} | LON ${Math.abs(lng).toFixed(4)}° ${ew}`;
    });

    map.on("click", (ev) => {
      if (!state.passes.length) return;
      const { lat, lng } = ev.latlng;
      if (lat < 3 || lat > 27 || lng < 63 || lng > 99) return;
      let nearest = null;
      let bestDist = 1e9;
      state.passes.forEach((p) => {
        const d = map.distance([lat, lng], [p.center_lat, p.center_lon]);
        if (d < bestDist) {
          bestDist = d;
          nearest = p;
        }
      });
      if (nearest && bestDist <= 650000) {
        activateSectorPass(nearest.id, true);
      }
    });
  }

  function renderStaticGisLayers(layers) {
    layerGroups.eez.clearLayers();
    layerGroups.infra.clearLayers();

    if (layers.coastline) {
      coastlineGeoJsonLayer = L.geoJSON(layers.coastline, {
        style: {
          color: "#475569",
          weight: 1.4,
          fillColor: "#1E293B",
          fillOpacity: 0.25,
          opacity: 0.72,
        },
        interactive: false,
      }).addTo(layerGroups.eez);
      updateCoastlineStyle();
    }

    if (layers.eez_boundary) {
      L.geoJSON(layers.eez_boundary, {
        style: {
          color: "#38BDF8",
          weight: 2,
          dashArray: "7, 6",
          opacity: 0.82,
        },
        onEachFeature: (feat, lyr) => {
          lyr.bindTooltip(feat.properties.name || "Indian EEZ", { sticky: true });
        },
      }).addTo(layerGroups.eez);
    }

    if (layers.shipping_lanes) {
      L.geoJSON(layers.shipping_lanes, {
        style: {
          color: "#64748B",
          weight: 1.4,
          dashArray: "3, 5",
          opacity: 0.65,
        },
        onEachFeature: (feat, lyr) => {
          lyr.bindTooltip(feat.properties.name || "Shipping Corridor", { sticky: true });
        },
      }).addTo(layerGroups.eez);
    }

    if (layers.restricted_zones) {
      L.geoJSON(layers.restricted_zones, {
        style: {
          color: "#F59E0B",
          weight: 1.4,
          fillColor: "#F59E0B",
          fillOpacity: 0.08,
          dashArray: "4, 4",
        },
        onEachFeature: (feat, lyr) => {
          lyr.bindTooltip(
            `<strong>${feat.properties.name}</strong><br/>${feat.properties.zone_type}`,
            { sticky: true }
          );
        },
      }).addTo(layerGroups.eez);
    }

    if (layers.critical_infrastructure) {
      L.geoJSON(layers.critical_infrastructure, {
        pointToLayer: (feat, latlng) =>
          L.circleMarker(latlng, {
            radius: 5.5,
            color: "#38BDF8",
            fillColor: "#0EA5E9",
            fillOpacity: 0.9,
            weight: 1.5,
          }),
        onEachFeature: (feat, lyr) => {
          lyr.bindTooltip(
            `<strong>${feat.properties.name}</strong><br/>${feat.properties.infra_type}`
          );
        },
      }).addTo(layerGroups.infra);
    }
  }

  function renderOrbitalTracks(constellation) {
    layerGroups.orbit.clearLayers();
    if (!constellation || !constellation.satellites) return;

    const palette = ["#A855F7", "#06B6D4", "#38BDF8"];
    constellation.satellites.forEach((sat, idx) => {
      const color = palette[idx % palette.length];
      (sat.track_segments || []).forEach((seg) => {
        const latlngs = seg.map(([lon, lat]) => [lat, lon]);
        L.polyline(latlngs, {
          color,
          weight: 1.5,
          dashArray: "5, 5",
          opacity: 0.55,
        }).addTo(layerGroups.orbit);
      });

      const satIcon = L.divIcon({
        className: "sat-orbit-icon",
        html: `<div style="background:${color};color:#0B1120;font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700;padding:2px 5px;border-radius:4px;white-space:nowrap;border:1px solid #fff;">SAT ${sat.satellite_name}</div>`,
        iconSize: [120, 18],
        iconAnchor: [60, 9],
      });
      L.marker([sat.subsat_lat, sat.subsat_lon], { icon: satIcon })
        .bindTooltip(
          `${sat.satellite_name} (NORAD ${sat.norad_id})<br/>Alt: ${sat.altitude_km} km | Vel: ${sat.velocity_km_s} km/s`
        )
        .addTo(layerGroups.orbit);
    });

    const syncEl = $("spaceSyncStatus");
    if (constellation.celestrak_live) {
      syncEl.classList.add("live");
      syncEl.innerHTML = `<span class="dot"></span><span>SPACE LINK: CELESTRAK LIVE</span>`;
    } else {
      syncEl.classList.remove("live");
      syncEl.innerHTML = `<span class="dot"></span><span>SPACE LINK: TLE CACHED</span>`;
    }

    const tbody = $("constellationTable").querySelector("tbody");
    tbody.innerHTML = "";
    constellation.satellites.forEach((sat) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${sat.satellite_name}</strong></td>
        <td>${sat.norad_id}</td>
        <td>${sat.band} / ${sat.swath_width_km} km</td>
        <td>${sat.altitude_km}</td>
        <td>${sat.velocity_km_s}</td>
        <td>${sat.inclination_deg}°</td>
        <td>${sat.subsat_lat.toFixed(2)}°, ${sat.subsat_lon.toFixed(2)}°</td>
        <td>${sat.source === "LIVE_CELESTRAK" ? "LIVE" : "CACHED"}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderAllSwathAreas(activePassId) {
    layerGroups.swath.clearLayers();
    state.passes.forEach((p) => {
      if (!p.swath_geojson) return;
      const isActive = p.id === activePassId;
      const total = p.scan_metrics?.total_scanned ?? "";
      const dark = p.scan_metrics?.dark_vessels_flagged ?? "";
      const countNote = total !== "" ? ` • ${total} vessels (${dark} dark)` : "";

      const layer = L.geoJSON(p.swath_geojson, {
        style: isActive
          ? { color: "#22D3EE", weight: 2.8, fillColor: "#06B6D4", fillOpacity: 0.14 }
          : { color: "#06B6D4", weight: 1.8, dashArray: "6, 5", fillColor: "#06B6D4", fillOpacity: 0.07 },
      });
      layer.bindTooltip(
        `<strong>${isActive ? "ACTIVE AREA" : "CLICK TO INSPECT"}: ${p.sector_name}</strong><br/>${p.satellite_name} (NORAD ${p.norad_id})${countNote}`,
        { sticky: true }
      );
      layer.on("mouseover", () => {
        if (p.id !== state.currentPassId) layer.setStyle({ fillOpacity: 0.22, weight: 2.4 });
      });
      layer.on("mouseout", () => {
        if (p.id !== state.currentPassId) layer.setStyle({ fillOpacity: 0.07, weight: 1.8 });
      });
      layer.on("click", (ev) => {
        L.DomEvent.stopPropagation(ev);
        activateSectorPass(p.id, true);
      });
      layer.addTo(layerGroups.swath);
    });
  }

  function renderVesselsOnMap(vessels) {
    layerGroups.ais.clearLayers();
    layerGroups.dark.clearLayers();
    markerByVesselId.clear();

    vessels.forEach((v) => {
      if (v.is_dark_vessel) {
        const icon = L.divIcon({
          className: "dark-marker-wrap",
          html: `<div class="dark-pulse-marker"><div class="dark-pulse-ring"></div><div class="dark-pulse-core"></div></div>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        });
        const marker = L.marker([v.latitude, v.longitude], { icon, zIndexOffset: 500 });
        marker.bindTooltip(
          `<strong>${v.target_code}</strong> • DARK VESSEL (${v.risk_level})<br/>${v.hull_length_m}m hull | AI Conf: ${v.ai_confidence}%`
        );
        marker.on("click", () => selectVessel(v.id));
        marker.addTo(layerGroups.dark);
        markerByVesselId.set(v.id, marker);
      } else {
        const warnCls = v.navic_gnss_anomaly ? " gnss-warn" : "";
        const icon = L.divIcon({
          className: "ais-marker-wrap",
          html: `<div class="ais-marker-dot${warnCls}"></div>`,
          iconSize: [11, 11],
          iconAnchor: [5, 5],
        });
        const marker = L.marker([v.latitude, v.longitude], { icon });
        marker.bindTooltip(
          `<strong>${v.vessel_name}</strong> (MMSI ${v.ais_mmsi || "--"})<br/>Verified AIS • ${v.hull_length_m}m`
        );
        marker.on("click", () => selectVessel(v.id));
        marker.addTo(layerGroups.ais);
        markerByVesselId.set(v.id, marker);
      }
    });
  }

  function renderAlertFeed() {
    const listEl = $("alertFeedList");
    listEl.innerHTML = "";

    const filtered = state.vessels.filter((v) => {
      if (state.currentFilter === "DARK") return v.is_dark_vessel;
      if (state.currentFilter === "HIGH") return v.risk_level === "HIGH";
      if (state.currentFilter === "VERIFIED") return !v.is_dark_vessel;
      return true;
    });

    $("feedCounter").textContent = `${filtered.length} TARGETS`;

    if (!filtered.length) {
      listEl.innerHTML = `<div class="vc-meta" style="padding:12px;">No contacts match filter.</div>`;
      return;
    }

    filtered.forEach((v) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `vessel-card${v.is_dark_vessel ? " is-dark" : ""}${
        state.selectedVesselId === v.id ? " selected" : ""
      }`;
      btn.setAttribute("role", "listitem");

      const aisTag = v.is_dark_vessel
        ? `NO AIS • ${v.nearest_ais_distance_km.toFixed(1)} km gap`
        : `MMSI ${v.ais_mmsi}`;
      const navicBadge = v.navic_gnss_anomaly ? `<span class="gnss-chip">GNSS WARN</span>` : "";

      btn.innerHTML = `
        <div class="vc-top">
          <span class="vc-code mono">${v.target_code}</span>
          <span class="risk-badge risk-${v.risk_level}">${v.risk_level}</span>
        </div>
        <div class="vc-name">${v.vessel_name}</div>
        <div class="vc-meta mono">
          <span class="vc-meta-left"><span>${v.hull_length_m}m | ${aisTag}</span>${navicBadge}</span>
          <span>${v.ai_confidence}%</span>
        </div>
      `;
      btn.addEventListener("click", () => {
        map.flyTo([v.latitude, v.longitude], 9, { duration: 0.7 });
        selectVessel(v.id);
      });
      listEl.appendChild(btn);
    });
  }

  function updateKpis(kpis, physicsEcon) {
    if (!kpis) return;
    const total = kpis.total_scanned ?? 0;
    const dark = kpis.dark_vessels_flagged ?? 0;
    const hrs = kpis.patrol_hours_saved ?? 0;
    const lakh = kpis.est_cost_saved_lakh ?? 0;

    $("kpiTotalScanned").textContent = `${total} Vessels`;
    $("kpiDarkFlagged").textContent = `${dark} Alert${dark === 1 ? "" : "s"}`;
    $("kpiCostSaved").textContent = `₹${lakh.toFixed(1)}L (${hrs}h)`;

    if (physicsEcon && physicsEcon.edge_ai) {
      $("edgePayloadKb").textContent = `<50 KB (${physicsEcon.edge_ai.onboard_alert_payload_kb} KB)`;
      $("edgeCompRatio").textContent = physicsEcon.edge_ai.compression_ratio;
    }
  }

  function updatePassMetadata(passObj, kpis = null) {
    if (!passObj) return;
    $("areaTitle").textContent = passObj.sector_name;
    $("passSatBadge").textContent = passObj.satellite_name;
    $("satNameNorad").textContent = `${passObj.satellite_name} (#${passObj.norad_id})`;
    $("satOrbitAlt").textContent = `${passObj.orbit_altitude_km || 693} km SSO`;
    $("satVelPeriod").textContent = `${passObj.orbital_velocity_km_s || 7.51} km/s • ${passObj.orbital_period_min || 98.6}m`;
    $("satBandSwath").textContent = `C-Band • ${passObj.swath_width_km || 250} km`;
    $("metaPassTime").textContent = formatUtcShort(passObj.pass_timestamp);
    $("metaIncidence").textContent = `${passObj.incidence_angle_deg || 36.2}° IW`;

    const metrics = kpis || passObj.scan_metrics || {};
    const countSuffix =
      typeof metrics.total_scanned === "number"
        ? ` (${metrics.total_scanned} vessels, ${metrics.dark_vessels_flagged} dark)`
        : "";
    const sceneLabel = (passObj.asf_scene_id || `${(passObj.sector_code || "SAR").toUpperCase()}`) + countSuffix;
    $("metaSceneId").textContent = sceneLabel;
    $("metaSceneId").title = sceneLabel;

    if (typeof passObj.center_lat === "number" && typeof passObj.center_lon === "number") {
      const ns = passObj.center_lat >= 0 ? "N" : "S";
      const ew = passObj.center_lon >= 0 ? "E" : "W";
      $("hudCoords").textContent = `LAT ${Math.abs(passObj.center_lat).toFixed(4)}° ${ns} | LON ${Math.abs(passObj.center_lon).toFixed(4)}° ${ew}`;
    }
  }

  async function activateSectorPass(passId, flyToArea = true) {
    const passObj = state.passes.find((p) => p.id === passId);
    if (!passObj) return;
    state.currentPassId = passId;
    state.selectedVesselId = null;
    $("inspectorDrawer").setAttribute("aria-hidden", "true");
    updatePassMetadata(passObj);
    renderAllSwathAreas(passId);
    if (flyToArea) {
      map.flyTo([passObj.center_lat, passObj.center_lon], passObj.default_zoom || 8, { duration: 0.75 });
    }
    await runFusionScan(passId, false);
  }

  async function runFusionScan(passId, showSweep = true) {
    const btn = $("runScanBtn");
    const label = $("runScanLabel");
    const overlay = $("scanSweepOverlay");
    btn.disabled = true;
    label.textContent = "Scanning...";
    $("hudScanState").textContent = "RUNNING AI FUSION...";
    if (showSweep) overlay.classList.remove("hidden");

    try {
      const [resp] = await Promise.all([
        fetch(`/api/scan/${passId}/`, { method: "POST" }),
        showSweep ? new Promise((r) => setTimeout(r, 900)) : Promise.resolve(),
      ]);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      state.vessels = data.vessels || [];
      state.physicsEconomics = data.physics_economics || state.physicsEconomics;

      updateKpis(data.kpis, data.physics_economics);
      updatePassMetadata(data.pass, data.kpis);
      renderAllSwathAreas(passId);
      renderVesselsOnMap(state.vessels);
      renderAlertFeed();

      $("hudScanState").textContent = `FUSION COMPLETE (${data.kpis.dark_vessels_flagged} DARK)`;
      showToast(
        `Area Loaded (${data.pass.sector_name}): ${data.kpis.legal_vessels} AIS verified, ${data.kpis.dark_vessels_flagged} dark vessels.`
      );
    } catch (err) {
      console.error(err);
      $("hudScanState").textContent = "SCAN ERROR";
      showToast("Error executing BhuArtha SAR+AIS fusion scan.");
    } finally {
      btn.disabled = false;
      label.textContent = "Run AI Scan";
      overlay.classList.add("hidden");
    }
  }

  async function selectVessel(vesselId) {
    state.selectedVesselId = vesselId;
    renderAlertFeed();

    const drawer = $("inspectorDrawer");
    drawer.setAttribute("aria-hidden", "false");
    $("inspChipLoader").classList.remove("hidden");

    try {
      const resp = await fetch(`/api/vessel/${vesselId}/`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const { vessel } = await resp.json();
      state.selectedVesselDetail = vessel;

      $("inspTargetCode").textContent = vessel.target_code;
      const riskEl = $("inspRiskBadge");
      riskEl.textContent = vessel.is_dark_vessel ? `DARK • ${vessel.risk_level} RISK` : `VERIFIED • ${vessel.risk_level}`;
      riskEl.className = `risk-badge risk-${vessel.risk_level}`;

      $("inspVesselName").textContent = vessel.vessel_name;
      $("inspVesselClass").textContent = `${vessel.vessel_type} • Spotted by ${vessel.satellite_name}`;

      const sumCard = $("inspSummaryCard");
      sumCard.classList.toggle("is-dark", Boolean(vessel.is_dark_vessel));
      $("inspSummaryBadge").textContent = vessel.is_dark_vessel ? "DARK VESSEL ALERT — PLAIN SUMMARY" : "VERIFIED SHIP — PLAIN SUMMARY";
      $("inspHumanSummary").textContent = vessel.human_summary || "";

      $("inspCoords").textContent = formatLatLon(vessel.latitude, vessel.longitude);
      $("inspHull").textContent = vessel.human_size || `${vessel.hull_length_m} m`;
      $("inspRcs").textContent = `${vessel.radar_cross_section_dbsm} dBsm`;
      $("inspAis").textContent = vessel.has_ais ? `ON — MMSI ${vessel.ais_mmsi}` : "OFF — No Signal (Dark)";
      $("inspNearestAis").textContent = `${vessel.nearest_ais_distance_km.toFixed(1)} km away`;
      $("inspLaneDist").textContent = `${vessel.nearest_lane_distance_km.toFixed(1)} km away`;
      $("inspEezDist").textContent = `${vessel.eez_distance_nm.toFixed(1)} NM inside EEZ`;
      $("inspKinematics").textContent = vessel.sar_chip?.source_label || "Real Sentinel-1 SAR";

      const navicBox = $("inspNavicBox");
      navicBox.classList.toggle("anomaly", Boolean(vessel.is_dark_vessel || vessel.navic_gnss_anomaly));
      $("inspNavicText").textContent = vessel.navic_status_note || "Tracking & timing nominal";

      $("inspAiConfVal").textContent = `${vessel.ai_confidence}%`;
      $("inspAiConfBar").style.width = `${Math.min(100, vessel.ai_confidence)}%`;

      const anomPct = Math.round((vessel.anomaly_score || 0) * 100);
      const anomTier = anomPct >= 75 ? "High" : (anomPct >= 50 ? "Medium" : "Low");
      $("inspAnomalyVal").textContent = `${anomTier} (${anomPct}%)`;
      $("inspAnomalyBar").style.width = `${anomPct}%`;

      const reasonsEl = $("inspReasonsList");
      reasonsEl.innerHTML = "";
      (vessel.risk_reasons || []).forEach((r) => {
        const li = document.createElement("li");
        li.textContent = r;
        reasonsEl.appendChild(li);
      });

      if (vessel.sar_chip) {
        $("inspSarChipImg").src = vessel.sar_chip.chip_data_uri;
        $("inspCfarSnr").textContent = `Signal ${vessel.sar_chip.cfar_snr_db} dB`;
        $("inspCfarLen").textContent = `Boat Length: ${vessel.sar_chip.cfar_estimated_length_m} m`;
        $("inspCfarPixels").textContent = `Radar Pixels: ${vessel.sar_chip.cfar_pixels}`;
      }
      $("officerNotesInput").value = "";
    } catch (err) {
      console.error(err);
      showToast("Failed to load vessel telemetry.");
    } finally {
      $("inspChipLoader").classList.add("hidden");
    }
  }

  function triggerFileDownload(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function openEvidenceModal(report, chipDataUri = null) {
    state.activeReport = report;
    const snap = report.snapshot_payload || {};
    const t = snap.target || {};
    const s = snap.satellite || {};

    $("evdReportCode").textContent = report.report_code;
    const stEl = $("evdStatusBadge");
    stEl.textContent = report.status;
    stEl.classList.toggle("dispatched", report.status === "DISPATCHED");
    $("dispatchEvidenceBtn").textContent =
      report.status === "DISPATCHED" ? "Re-Export Dispatched Report (HTML)" : "Dispatch / Export Evidence";

    $("evdTargetCode").textContent = `${t.target_code || report.target_code} (${t.vessel_name || report.vessel_name})`;
    $("evdAis").textContent = t.ais_status_label || (t.has_ais ? `MMSI ${t.ais_mmsi}` : "DARK — NO TRANSPONDER PING");
    $("evdRiskConf").textContent = `${t.risk_level || "--"} RISK • ${t.ai_confidence || "--"}% CONF`;
    $("evdCoords").textContent = formatLatLon(t.latitude || 0, t.longitude || 0);
    $("evdSector").textContent = s.sector || report.sector_name || "--";
    $("evdGenTime").textContent = formatUtcAndIst(snap.generated_at_utc || report.created_at);
    $("evdHullRcs").textContent = `${t.hull_length_m || "--"}m × ${t.hull_width_m || "--"}m | ${t.radar_cross_section_dbsm || "--"} dBsm (SNR ${t.cfar_snr_db || "--"} dB)`;
    $("evdGeoOffset").textContent = `${t.eez_distance_nm || "--"} NM from outer EEZ | ${t.nearest_lane_distance_km || "--"} km off lane`;
    $("evdSatellite").textContent = `${s.name || "--"} (NORAD ${s.norad_id || "--"}) @ ${formatUtcShort(s.pass_timestamp)}`;
    $("evdNotes").textContent = report.officer_notes || "--";
    $("evdHash").textContent = report.evidence_hash || "--";

    const reasonsList = $("evdReasonsList");
    reasonsList.innerHTML = "";
    (t.risk_reasons || []).forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      reasonsList.appendChild(li);
    });

    const imgEl = $("evdChipImg");
    if (chipDataUri) {
      imgEl.src = chipDataUri;
    } else if (state.selectedVesselDetail && state.selectedVesselDetail.sar_chip) {
      imgEl.src = state.selectedVesselDetail.sar_chip.chip_data_uri;
    }

    $("evidenceModal").classList.remove("hidden");
  }

  async function generateEvidencePacket(autoDispatchAndExport = false) {
    if (!state.selectedVesselId) return;
    const btn = autoDispatchAndExport ? $("quickDispatchExportBtn") : $("generateEvidenceBtn");
    btn.disabled = true;
    try {
      const resp = await fetch(`/api/evidence/${state.selectedVesselId}/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          officer_notes: $("officerNotesInput").value,
          dispatch: autoDispatchAndExport,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      openEvidenceModal(data.report, data.report.sar_chip_data_uri);
      await refreshEvidenceCount();

      if (autoDispatchAndExport) {
        triggerFileDownload(
          data.report.export_html_url,
          `BhuArtha-Evidence-${data.report.report_code}.html`
        );
        showToast(`Dispatched ${data.report.report_code} and downloaded standalone HTML report.`);
      } else {
        showToast(`BhuArtha Evidence Packet ${data.report.report_code} logged with SHA-256 digest.`);
      }
    } catch (err) {
      console.error(err);
      showToast("Failed to generate evidence packet.");
    } finally {
      btn.disabled = false;
    }
  }

  async function dispatchAndExportActiveReport() {
    if (!state.activeReport) return;
    const resp = await fetch(`/api/evidence/${state.activeReport.id}/dispatch/`, { method: "POST" });
    if (resp.ok) {
      const { report } = await resp.json();
      openEvidenceModal(report);
      await refreshEvidenceCount();
      triggerFileDownload(
        report.export_html_url || `/api/evidence/${report.id}/export/?format=html`,
        `BhuArtha-Evidence-${report.report_code}.html`
      );
      showToast(`Dispatched ${report.report_code} to ICG & downloaded printable HTML report.`);
    }
  }

  async function refreshEvidenceCount() {
    try {
      const resp = await fetch("/api/evidence/");
      if (!resp.ok) return [];
      const { reports } = await resp.json();
      $("evidenceCountChip").textContent = String((reports || []).length);
      return reports || [];
    } catch {
      return [];
    }
  }

  async function openEvidenceLogModal() {
    const reports = await refreshEvidenceCount();
    const body = $("evidenceLogBody");
    body.innerHTML = "";
    if (!reports.length) {
      body.innerHTML = `<p style="color:var(--text-secondary);">No evidence packets generated yet. Click any Dark Vessel alert and choose "Generate & Inspect Evidence" or "Dispatch / Export Evidence".</p>`;
    } else {
      reports.forEach((r) => {
        const row = document.createElement("div");
        row.className = "evd-log-row";
        row.innerHTML = `
          <div class="evd-log-info">
            <div><strong>${r.report_code}</strong> • <span class="risk-badge risk-${
          (r.snapshot_payload?.target?.risk_level) || "HIGH"
        }">${r.status}</span></div>
            <div class="evd-log-sub">${r.target_code} (${r.vessel_name}) — ${r.sector_name} • ${formatUtcShort(r.created_at)}</div>
          </div>
          <div style="display:flex;gap:6px;">
            <a class="btn btn-secondary" href="${r.export_html_url}" download="BhuArtha-Evidence-${r.report_code}.html">HTML</a>
            <button type="button" class="btn btn-primary">Inspect</button>
          </div>
        `;
        row.querySelector("button").addEventListener("click", async () => {
          $("evidenceLogModal").classList.add("hidden");
          const vResp = await fetch(`/api/vessel/${r.detection_id}/`);
          let chipUri = null;
          if (vResp.ok) {
            const vData = await vResp.json();
            chipUri = vData.vessel?.sar_chip?.chip_data_uri || null;
          }
          openEvidenceModal(r, chipUri);
        });
        body.appendChild(row);
      });
    }
    $("evidenceLogModal").classList.remove("hidden");
  }

  function updateRoiCalculator() {
    const costHr = parseFloat($("roiCostHr").value);
    const alertsYr = parseFloat($("roiAlertsYr").value);
    const hrsCue = parseFloat($("roiHrsCue").value);
    const licenseCr = parseFloat($("roiLicense").value);

    $("roiCostHrVal").textContent = `₹${costHr.toFixed(1)} Lakh/hr`;
    $("roiAlertsYrVal").textContent = `${alertsYr} vessels`;
    $("roiHrsCueVal").textContent = `${hrsCue.toFixed(1)} hrs`;
    $("roiLicenseVal").textContent = `₹${licenseCr.toFixed(1)} Crore/yr`;

    const hoursSaved = alertsYr * hrsCue;
    const savingsCrore = (hoursSaved * costHr) / 100.0;
    const multiple = savingsCrore / licenseCr;
    const breakevenHrs = (licenseCr * 100.0) / costHr;

    $("roiOutHours").textContent = `${hoursSaved.toFixed(1)} hrs`;
    $("roiOutSavings").textContent = `₹${savingsCrore.toFixed(2)} Cr`;
    $("roiOutMultiple").textContent = `${multiple.toFixed(2)}x`;
    $("roiOutBreakeven").textContent = `${breakevenHrs.toFixed(1)} hrs`;
  }

  function bindLayerToggles() {
    const bind = (checkboxId, groupKey) => {
      $(checkboxId).addEventListener("change", (e) => {
        if (e.target.checked) {
          map.addLayer(layerGroups[groupKey]);
        } else {
          map.removeLayer(layerGroups[groupKey]);
        }
      });
    };
    bind("layerSwath", "swath");
    bind("layerAis", "ais");
    bind("layerDark", "dark");
    bind("layerEez", "eez");
    bind("layerInfra", "infra");
    bind("layerOrbit", "orbit");
  }

  function bindUiEvents() {
    $("sidebarToggleBtn").addEventListener("click", () => {
      $("leftSidebar").classList.toggle("open");
    });

    $("resetIndiaViewBtn").addEventListener("click", () => {
      map.flyTo([14.2, 82.0], 5, { duration: 0.7 });
      showToast("Showing all 4 Indian maritime radar areas — click any cyan box to inspect.");
    });

    $("runScanBtn").addEventListener("click", () => {
      if (state.currentPassId) runFusionScan(state.currentPassId, true);
    });

    document.querySelectorAll(".view-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.mode === "satellite" ? "satellite" : "dark";
        document.querySelectorAll(".view-mode-btn").forEach((b) => {
          const isMatch = b.dataset.mode === mode;
          b.classList.toggle("active", isMatch);
          b.setAttribute("aria-pressed", isMatch ? "true" : "false");
        });
        setBasemapStage(0, mode);
      });
    });

    document.querySelectorAll(".filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        state.currentFilter = pill.dataset.filter;
        renderAlertFeed();
      });
    });

    $("closeInspectorBtn").addEventListener("click", () => {
      $("inspectorDrawer").setAttribute("aria-hidden", "true");
      state.selectedVesselId = null;
      renderAlertFeed();
    });

    $("generateEvidenceBtn").addEventListener("click", () => generateEvidencePacket(false));
    $("quickDispatchExportBtn").addEventListener("click", () => generateEvidencePacket(true));

    $("openPhysicsModalBtn").addEventListener("click", () => {
      $("physicsModal").classList.remove("hidden");
    });
    $("closePhysicsModalBtn").addEventListener("click", () => {
      $("physicsModal").classList.add("hidden");
    });

    $("openEvidenceLogBtn").addEventListener("click", openEvidenceLogModal);
    $("closeEvidenceLogBtn").addEventListener("click", () => {
      $("evidenceLogModal").classList.add("hidden");
    });
    $("closeEvidenceModalBtn").addEventListener("click", () => {
      $("evidenceModal").classList.add("hidden");
    });

    $("printEvidenceBtn").addEventListener("click", () => window.print());

    $("downloadEvidenceJsonBtn").addEventListener("click", () => {
      if (!state.activeReport) return;
      triggerFileDownload(
        state.activeReport.export_json_url || `/api/evidence/${state.activeReport.id}/export/?format=json`,
        `BhuArtha-Evidence-${state.activeReport.report_code}.json`
      );
    });

    $("dispatchEvidenceBtn").addEventListener("click", dispatchAndExportActiveReport);

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        $(btn.dataset.tab).classList.add("active");
      });
    });

    ["roiCostHr", "roiAlertsYr", "roiHrsCue", "roiLicense"].forEach((id) => {
      $(id).addEventListener("input", updateRoiCalculator);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $("evidenceModal").classList.add("hidden");
        $("physicsModal").classList.add("hidden");
        $("evidenceLogModal").classList.add("hidden");
      }
    });

    ["evidenceModal", "physicsModal", "evidenceLogModal"].forEach((mId) => {
      $(mId).addEventListener("click", (e) => {
        if (e.target.id === mId) $(mId).classList.add("hidden");
      });
    });
  }

  async function bootstrap() {
    initMap();
    bindLayerToggles();
    bindUiEvents();
    updateRoiCalculator();

    try {
      const resp = await fetch("/api/passes/");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      if (data.database) {
        const badge = $("dbStatusBadge");
        badge.textContent = data.database.label;
        badge.className = `db-pill ${data.database.mode === "SUPABASE_LIVE" ? "db-live" : "db-fallback"}`;
      }

      state.passes = data.passes || [];
      state.constellation = data.constellation;
      state.physicsEconomics = data.physics_economics;
      state.gisLayers = data.layers;

      renderStaticGisLayers(data.layers || {});
      renderOrbitalTracks(data.constellation || {});

      if (state.passes.length > 0) {
        map.setView([14.2, 82.0], 5);
        await activateSectorPass(state.passes[0].id, false);
      }
      await refreshEvidenceCount();
    } catch (err) {
      console.error(err);
      showToast("Failed to connect to BhuArtha Django backend.");
    }
  }

  document.addEventListener("DOMContentLoaded", bootstrap);
})();
