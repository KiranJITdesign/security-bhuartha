"""Real Sentinel-1 SAR patch extractor & 2D CA-CFAR detector with disk chip cache."""

import base64
from io import BytesIO
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, label, uniform_filter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHIP_CACHE_PATH = DATA_DIR / "cached_chips.json"
_MEMORY_CHIP_CACHE: Dict[str, Dict] = {}
_SCENE_IMAGE_CACHE: Dict[str, Image.Image] = {}


def _chip_cache_key(seed: int, hull_length_m: float, is_dark: bool, scene_tag: str = "") -> str:
    return f"{scene_tag}:{int(seed)}:{round(float(hull_length_m), 1)}:{1 if is_dark else 0}"


def _load_disk_chip_cache() -> Dict[str, Dict]:
    if _MEMORY_CHIP_CACHE:
        return _MEMORY_CHIP_CACHE
    if CHIP_CACHE_PATH.exists():
        try:
            data = json.loads(CHIP_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _MEMORY_CHIP_CACHE.update(data)
        except Exception:
            pass
    return _MEMORY_CHIP_CACHE


def _get_real_sar_scene_image(browse_rel_path: str) -> Optional[Image.Image]:
    if not browse_rel_path:
        return None
    if browse_rel_path in _SCENE_IMAGE_CACHE:
        return _SCENE_IMAGE_CACHE[browse_rel_path]
    full_path = DATA_DIR / browse_rel_path
    if full_path.exists():
        im = Image.open(full_path).convert("RGB")
        _SCENE_IMAGE_CACHE[browse_rel_path] = im
        return im
    return None


def simulate_sar_patch(
    hull_length_m: float,
    hull_width_m: float,
    rcs_dbsm: float,
    heading_deg: float,
    seed: int = 101,
    patch_px: int = 128,
    pixel_spacing_m: float = 5.0,
) -> np.ndarray:
    """Fallback Gamma speckle SAR patch used only when an external scene image is absent."""
    rng = np.random.default_rng(seed)
    clutter = rng.gamma(shape=4.0, scale=0.045, size=(patch_px, patch_px))
    yy, xx = np.mgrid[0:patch_px, 0:patch_px]
    swell = 0.025 * np.sin(0.18 * xx + 0.11 * yy + (seed % 7))
    patch = np.clip(clutter + swell, 0.02, 0.55)

    cx, cy = patch_px / 2.0, patch_px / 2.0
    theta = np.radians(heading_deg)
    dx = xx - cx
    dy = yy - cy
    along = dx * np.sin(theta) - dy * np.cos(theta)
    across = dx * np.cos(theta) + dy * np.sin(theta)

    half_len_px = max(2.0, (hull_length_m / pixel_spacing_m) / 2.0)
    half_wid_px = max(1.2, (hull_width_m / pixel_spacing_m) / 2.0)
    hull_mask = ((along / half_len_px) ** 2 + (across / half_wid_px) ** 2) <= 1.0
    rcs_linear = 0.65 + min(1.85, max(0.2, (rcs_dbsm - 8.0) / 14.0))
    glint = np.exp(-((along ** 2) / (0.45 * half_len_px ** 2) + (across ** 2) / (0.65 * half_wid_px ** 2)))
    patch += hull_mask.astype(float) * (0.55 * rcs_linear) + glint * (0.45 * rcs_linear)
    return np.clip(patch, 0.01, 3.0)


def run_2d_ca_cfar(
    patch: np.ndarray,
    guard_radius: int = 4,
    train_radius: int = 14,
    alpha: float = 3.2,
    valid_mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, float, Tuple[int, int, int, int]]:
    """Execute 2D Cell-Averaging CFAR detection on radar intensity and locate central hull."""
    train_size = 2 * train_radius + 1
    guard_size = 2 * guard_radius + 1

    work = patch.astype(float)
    if valid_mask is not None and np.any(valid_mask):
        fill_val = float(np.median(work[valid_mask]))
        work = np.where(valid_mask, work, fill_val)

    train_sum = uniform_filter(work, size=train_size, mode="reflect") * (train_size ** 2)
    guard_sum = uniform_filter(work, size=guard_size, mode="reflect") * (guard_size ** 2)
    n_train = max(1, (train_size ** 2) - (guard_size ** 2))
    bg_mean = (train_sum - guard_sum) / n_train

    sq_train_sum = uniform_filter(work ** 2, size=train_size, mode="reflect") * (train_size ** 2)
    sq_guard_sum = uniform_filter(work ** 2, size=guard_size, mode="reflect") * (guard_size ** 2)
    bg_var = np.maximum(1e-6, ((sq_train_sum - sq_guard_sum) / n_train) - (bg_mean ** 2))
    bg_std = np.sqrt(bg_var)

    threshold = bg_mean + alpha * bg_std
    raw_det = work > threshold
    if valid_mask is not None:
        raw_det &= valid_mask

    cy, cx = work.shape[0] // 2, work.shape[1] // 2
    labeled, num_features = label(binary_dilation(raw_det, iterations=1))
    target_mask = np.zeros_like(raw_det, dtype=bool)

    if num_features > 0:
        best_label = None
        best_dist = 1e9
        for lbl in range(1, num_features + 1):
            ys_l, xs_l = np.where(labeled == lbl)
            dist = float(np.hypot(np.mean(xs_l) - cx, np.mean(ys_l) - cy))
            if dist < 16.0 and dist < best_dist:
                best_dist = dist
                best_label = lbl
        if best_label is not None:
            target_mask = raw_det & (labeled == best_label)

    # Search tight 10px center neighborhood if target is compact (1-2 pixels on quicklook)
    win = work[max(0, cy - 8) : cy + 9, max(0, cx - 8) : cx + 9]
    peak_val = float(np.max(win)) if win.size else float(work[cy, cx])
    clutter_val = float(np.median(bg_mean[valid_mask])) if (valid_mask is not None and np.any(valid_mask)) else float(np.median(bg_mean))
    snr_db = 10.0 * np.log10(max(peak_val / max(clutter_val, 1e-4), 1.05))

    if np.any(target_mask):
        ys, xs = np.where(target_mask)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    else:
        # Center bounding box tightly around peak pixel in center window
        py, px = np.unravel_index(np.argmax(win), win.shape)
        gy, gx = max(0, cy - 8) + int(py), max(0, cx - 8) + int(px)
        target_mask[gy, gx] = True
        bbox = (max(0, gx - 2), max(0, gy - 2), min(work.shape[1] - 1, gx + 2), min(work.shape[0] - 1, gy + 2))

    return target_mask, round(float(snr_db), 2), bbox


def _extract_real_sar_crop(
    browse_rel_path: str,
    swath_geojson: Dict,
    lat: float,
    lon: float,
    crop_half: int = 48,
) -> Optional[Tuple[Image.Image, np.ndarray, np.ndarray]]:
    """Crop a 96x96 real Sentinel-1 SAR patch centered on (lat, lon)."""
    scene_im = _get_real_sar_scene_image(browse_rel_path)
    if scene_im is None or not swath_geojson:
        return None
    coords = swath_geojson.get("coordinates", [[]])[0]
    if len(coords) < 4:
        return None
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    if (max_lon - min_lon) < 1e-6 or (max_lat - min_lat) < 1e-6:
        return None

    w, h = scene_im.size
    cx = int(round((lon - min_lon) / (max_lon - min_lon) * (w - 1)))
    cy = int(round((max_lat - lat) / (max_lat - min_lat) * (h - 1)))

    x0 = max(0, min(w - 2 * crop_half, cx - crop_half))
    y0 = max(0, min(h - 2 * crop_half, cy - crop_half))
    x1 = min(w, x0 + 2 * crop_half)
    y1 = min(h, y0 + 2 * crop_half)

    crop_im = scene_im.crop((x0, y0, x1, y1))
    arr = np.array(crop_im, dtype=float)
    # In ASF VV+VH dual-pol quicklooks, metallic ships spike in Red+Green vs blue ocean
    intensity = (0.58 * arr[..., 0] + 0.42 * arr[..., 1]) / 255.0 + 0.02
    valid_mask = (arr[..., 0] + arr[..., 1] + arr[..., 2]) > 14.0
    return crop_im, intensity, valid_mask


def _compute_sar_chip_bundle(
    hull_length_m: float,
    hull_width_m: float,
    rcs_dbsm: float,
    heading_deg: float,
    seed: int = 101,
    is_dark: bool = True,
    browse_rel_path: str = "",
    swath_geojson: Optional[Dict] = None,
    lat: float = 0.0,
    lon: float = 0.0,
    scene_id: str = "",
) -> Dict:
    """Extract real Sentinel-1 SAR patch (if available), run 2D CA-CFAR & render annotated PNG."""
    real_crop = _extract_real_sar_crop(browse_rel_path, swath_geojson or {}, lat, lon)
    if real_crop is not None:
        crop_im, intensity, valid_mask = real_crop
        det_mask, snr_db, bbox = run_2d_ca_cfar(
            intensity, guard_radius=4, train_radius=14, alpha=3.2, valid_mask=valid_mask
        )
        base_size = crop_im.size[0]
        scale = 320.0 / max(1, base_size)
        img = crop_im.resize((320, 320), Image.Resampling.NEAREST)
        source_label = "REAL SENTINEL-1 SAR"
    else:
        patch = simulate_sar_patch(hull_length_m, hull_width_m, rcs_dbsm, heading_deg, seed=seed)
        det_mask, snr_db, bbox = run_2d_ca_cfar(patch, guard_radius=6, train_radius=16, alpha=4.2)
        norm = np.clip((np.log1p(patch * 4.5) / np.log1p(3.0 * 4.5)), 0.0, 1.0)
        rgb = np.zeros((patch.shape[0], patch.shape[1], 3), dtype=np.uint8)
        rgb[..., 0] = np.clip(11 + norm * 210, 0, 255).astype(np.uint8)
        rgb[..., 1] = np.clip(22 + norm * 230, 0, 255).astype(np.uint8)
        rgb[..., 2] = np.clip(45 + norm * 210, 0, 255).astype(np.uint8)
        scale = 320.0 / patch.shape[0]
        img = Image.fromarray(rgb, mode="RGB").resize((320, 320), Image.Resampling.NEAREST)
        source_label = "2D CA-CFAR PATCH"

    draw = ImageDraw.Draw(img, "RGBA")
    bx0, by0, bx1, by1 = bbox
    x0 = max(4, int(bx0 * scale) - 10)
    y0 = max(4, int(by0 * scale) - 10)
    x1 = min(315, int((bx1 + 1) * scale) + 10)
    y1 = min(315, int((by1 + 1) * scale) + 10)

    box_color = (239, 68, 68, 255) if is_dark else (16, 185, 129, 255)
    draw.rectangle([x0, y0, x1, y1], outline=box_color, width=2)

    draw.rectangle([6, 6, 255, 26], fill=(11, 17, 32, 215))
    draw.text((12, 11), f"{source_label} | SNR {snr_db:.1f} dB", fill=(6, 182, 212, 255))

    draw.rectangle([6, 282, 240, 312], fill=(11, 17, 32, 215))
    short_scene = (scene_id[:20] + "...") if len(scene_id) > 20 else (scene_id or "ASF GRD")
    draw.text((12, 291), f"CNN LEN: {hull_length_m:.1f}m | {short_scene}", fill=(226, 232, 240, 255))

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "cfar_snr_db": snr_db,
        "cfar_estimated_length_m": round(float(hull_length_m), 1),
        "cfar_pixels": int(np.sum(det_mask)),
        "source_label": source_label,
        "chip_data_uri": f"data:image/png;base64,{b64}",
    }


def generate_sar_chip_bundle(
    hull_length_m: float,
    hull_width_m: float,
    rcs_dbsm: float,
    heading_deg: float,
    seed: int = 101,
    is_dark: bool = True,
    browse_rel_path: str = "",
    swath_geojson: Optional[Dict] = None,
    lat: float = 0.0,
    lon: float = 0.0,
    scene_id: str = "",
) -> Dict:
    """Return pre-cached SAR CFAR chip bundle if available, else compute from real/fallback patch."""
    cache = _load_disk_chip_cache()
    key = _chip_cache_key(seed, hull_length_m, is_dark, scene_id)
    if key in cache:
        return dict(cache[key])

    bundle = _compute_sar_chip_bundle(
        hull_length_m=hull_length_m,
        hull_width_m=hull_width_m,
        rcs_dbsm=rcs_dbsm,
        heading_deg=heading_deg,
        seed=seed,
        is_dark=is_dark,
        browse_rel_path=browse_rel_path,
        swath_geojson=swath_geojson,
        lat=lat,
        lon=lon,
        scene_id=scene_id,
    )
    cache[key] = bundle
    return dict(bundle)


def prebuild_cached_chips(detections: List) -> int:
    """Rebuild SAR CFAR chip cache on disk from actual Sentinel-1 scene crops."""
    _MEMORY_CHIP_CACHE.clear()
    cache: Dict[str, Dict] = {}
    for det in detections:
        sat_pass = det.pass_ref
        metrics = sat_pass.scan_metrics or {}
        browse_rel = metrics.get("local_browse_path", "")
        key = _chip_cache_key(det.sar_chip_seed, det.hull_length_m, det.is_dark_vessel, sat_pass.asf_scene_id)
        cache[key] = _compute_sar_chip_bundle(
            hull_length_m=det.hull_length_m,
            hull_width_m=det.hull_width_m,
            rcs_dbsm=det.radar_cross_section_dbsm,
            heading_deg=det.heading_deg,
            seed=det.sar_chip_seed,
            is_dark=det.is_dark_vessel,
            browse_rel_path=browse_rel,
            swath_geojson=sat_pass.swath_geojson,
            lat=det.latitude,
            lon=det.longitude,
            scene_id=sat_pass.asf_scene_id,
        )
    CHIP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHIP_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    _MEMORY_CHIP_CACHE.update(cache)
    return len(cache)
