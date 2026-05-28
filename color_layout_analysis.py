# -*- coding: utf-8 -*-

import cv2
import numpy as np
import yaml
from collections import Counter


# =====================================================================
# 🎨 STEP 1 — DOMINANT COLOR EXTRACTION
# Uses K-Means clustering to find top N colors in the image.
# Returns hex codes + percentage share (for the Pie Chart).
# =====================================================================
def extract_dominant_colors(image_path, n_colors=5):
    """
    Extracts the top N dominant colors from a poster image using K-Means.

    Returns a list of dicts:
      [ { "hex": "#RRGGBB", "rgb": [R, G, B], "percentage": 40.2 }, ... ]
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Flatten to (total_pixels, 3) and convert to float32 for K-Means
    pixels = img_rgb.reshape(-1, 3).astype(np.float32)

    # Run K-Means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    _, labels, centers = cv2.kmeans(
        pixels, n_colors, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
    )

    centers = np.uint8(centers)
    label_counts = Counter(labels.flatten())
    total_pixels = len(labels)

    dominant_colors = []
    for i, center in enumerate(centers):
        r, g, b = int(center[0]), int(center[1]), int(center[2])
        hex_color = "#{:02X}{:02X}{:02X}".format(r, g, b)
        percentage = round((label_counts[i] / total_pixels) * 100, 1)
        dominant_colors.append({
            "hex": hex_color,
            "rgb": [r, g, b],
            "percentage": percentage
        })

    # Sort by most dominant first
    dominant_colors.sort(key=lambda x: x["percentage"], reverse=True)
    return dominant_colors


# =====================================================================
# 🔲 STEP 2 — BACKGROUND COLOR DETECTION
# Samples the image border edges to estimate the background color.
# =====================================================================
def detect_background_color(image_path, border_thickness=10):
    """
    Samples pixels along the image border to determine the background color.
    Returns { "hex": "#RRGGBB", "rgb": [R, G, B] }
    """
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    # Collect border pixels from all 4 edges
    border_pixels = np.concatenate([
        img_rgb[:border_thickness, :].reshape(-1, 3),          # top
        img_rgb[-border_thickness:, :].reshape(-1, 3),         # bottom
        img_rgb[:, :border_thickness].reshape(-1, 3),          # left
        img_rgb[:, -border_thickness:].reshape(-1, 3),         # right
    ])

    # Use median to avoid noise skewing the result
    bg_color = np.median(border_pixels, axis=0).astype(int)
    r, g, b = int(bg_color[0]), int(bg_color[1]), int(bg_color[2])
    return {
        "hex": "#{:02X}{:02X}{:02X}".format(r, g, b),
        "rgb": [r, g, b]
    }


# =====================================================================
# ⚖️ STEP 3 — WCAG CONTRAST RATIO MATH
# This is the core readability calculation for the dashboard.
#
# Formula source: WCAG 2.1 (Web Content Accessibility Guidelines)
#   Contrast Ratio = (L1 + 0.05) / (L2 + 0.05)
#   where L1 = lighter relative luminance, L2 = darker relative luminance
#
# Score interpretation (for dashboard bar chart):
#   >= 7.0  → AAA (Excellent)   → score 100
#   >= 4.5  → AA  (Good)        → score 75
#   >= 3.0  → AA Large (Fair)   → score 50
#   < 3.0   → Fail (Poor)       → score 25
# =====================================================================
def _relative_luminance(rgb):
    """Converts an RGB tuple to WCAG relative luminance (0.0–1.0)."""
    def linearize(channel):
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def calculate_contrast_ratio(color1_rgb, color2_rgb):
    """
    Calculates WCAG contrast ratio between two RGB colors.
    Returns a float between 1.0 and 21.0.
    """
    L1 = _relative_luminance(color1_rgb)
    L2 = _relative_luminance(color2_rgb)
    lighter = max(L1, L2)
    darker = min(L1, L2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def wcag_grade(contrast_ratio):
    """Returns WCAG grade label and a 0–100 readability score for the bar chart."""
    if contrast_ratio >= 7.0:
        return "AAA - Excellent", 100
    elif contrast_ratio >= 4.5:
        return "AA - Good", 75
    elif contrast_ratio >= 3.0:
        return "AA Large - Fair", 50
    else:
        return "Fail - Poor", 25


# =====================================================================
# 🔤 STEP 4 — TEXT COLOR SAMPLING
# For each OCR text region (from M2), sample the average pixel color
# inside the bounding box to determine the actual text color.
# =====================================================================
def sample_text_colors(image_path, spatial_manifest, max_samples=5):
    """
    Samples image pixels inside each OCR bounding box to approximate text color.

    Args:
        image_path: path to poster image
        spatial_manifest: list of OCR elements from M2's complete_spatial_manifest

    Returns a list of dicts with text + detected color hex.
    """
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    text_color_samples = []

    for item in spatial_manifest[:max_samples]:
        tl = item["bounding_box"]["top_left"]
        br = item["bounding_box"]["bottom_right"]

        # Clamp coordinates to image bounds
        x1, y1 = max(0, tl[0]), max(0, tl[1])
        x2, y2 = min(w, br[0]), min(h, br[1])

        if x2 <= x1 or y2 <= y1:
            continue

        region = img_rgb[y1:y2, x1:x2]

        # Approximate text color: darkest pixel cluster in the region
        # (text is usually darker than its background within the box)
        region_flat = region.reshape(-1, 3).astype(np.float32)
        brightness = region_flat.mean(axis=1)
        dark_pixels = region_flat[brightness < brightness.mean()]

        if len(dark_pixels) == 0:
            dark_pixels = region_flat

        avg_color = np.median(dark_pixels, axis=0).astype(int)
        r, g, b = int(avg_color[0]), int(avg_color[1]), int(avg_color[2])

        text_color_samples.append({
            "text_snippet": item["text"][:40],
            "text_color_hex": "#{:02X}{:02X}{:02X}".format(r, g, b),
            "text_color_rgb": [r, g, b],
            "bounding_box": item["bounding_box"]
        })

    return text_color_samples


# =====================================================================
# 📐 STEP 5 — TEXT DENSITY CALCULATION
# Computes the % of image area covered by OCR bounding boxes.
# Feeds the Text Density Chart in the dashboard.
# =====================================================================
def calculate_text_density(image_path, spatial_manifest):
    """
    Calculates what percentage of the image is covered by text regions.

    Returns:
        text_area_percent  (float): % of image covered by text
        visual_area_percent (float): remaining % (visual/image space)
    """
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    total_image_area = h * w

    text_area = 0
    for item in spatial_manifest:
        tl = item["bounding_box"]["top_left"]
        br = item["bounding_box"]["bottom_right"]
        region_w = max(0, br[0] - tl[0])
        region_h = max(0, br[1] - tl[1])
        text_area += region_w * region_h

    # Cap at 100% in case of overlapping boxes
    text_area_percent = min(round((text_area / total_image_area) * 100, 1), 100.0)
    visual_area_percent = round(100.0 - text_area_percent, 1)

    return text_area_percent, visual_area_percent


# =====================================================================
# 📊 STEP 6 — READABILITY SCORES (for the Bar Chart)
# Aggregates multiple sub-scores into a dashboard-ready dict.
# =====================================================================
def calculate_readability_scores(image_path, dominant_colors, background_color, blur_score, brightness):
    """
    Produces the 4 readability sub-scores for the bar chart:
      - Text Readability  (contrast ratio of top 2 dominant colors vs bg)
      - Contrast Quality  (WCAG grade converted to 0–100 score)
      - Image Quality     (derived from blur score + brightness)
      - Layout Clarity    (inverse of text density — less clutter = clearer)

    Returns a dict of { metric: score_0_to_100 }
    """
    scores = {}

    # --- Contrast Quality (text vs background) ---
    best_contrast = 1.0
    for color in dominant_colors[:3]:
        cr = calculate_contrast_ratio(color["rgb"], background_color["rgb"])
        if cr > best_contrast:
            best_contrast = cr
    _, contrast_score = wcag_grade(best_contrast)
    scores["contrast_quality"] = contrast_score

    # --- Image Quality (blur + brightness combined) ---
    # Blur: normalize laplacian variance. >800 = perfect. <300 = blurry (already failed M1).
    blur_normalized = min(round((blur_score / 800) * 100, 0), 100)
    # Brightness: ideal range 100–200. Score drops outside that.
    brightness_score = 100 - abs(brightness - 150) / 1.5
    brightness_score = max(0, min(100, round(brightness_score, 0)))
    scores["image_quality"] = round((blur_normalized + brightness_score) / 2, 0)

    # --- Text Readability (WCAG grade from best color pair) ---
    # Re-maps WCAG contrast score into a 0–100 readability score
    readability_raw = min(round((best_contrast / 21.0) * 100, 0), 100)
    scores["text_readability"] = readability_raw

    # Layout Clarity is calculated later once text density is known.
    # Placeholder here; filled in by compile_color_data().
    scores["layout_clarity"] = None

    scores["_best_contrast_ratio"] = best_contrast
    scores["_wcag_grade"] = wcag_grade(best_contrast)[0]

    return scores


# =====================================================================
# 📡 STEP 7 — CTA VISUAL ANALYSIS
# Scores CTA visibility, placement, and contrast using bounding box math.
# Feeds the CTA Effectiveness Chart in the dashboard.
# =====================================================================
def analyze_cta_visuals(image_path, detected_ctas, background_color):
    """
    For each CTA found by M2, scores:
      - Visibility   (size of CTA bounding box relative to image)
      - Placement    (is it in the bottom third? = strong CTA placement)
      - Contrast     (WCAG score of CTA region vs background)

    Returns a dict with scores + found/missing status.
    """
    if not detected_ctas:
        return {
            "cta_found": False,
            "cta_count": 0,
            "visibility_score": 0,
            "placement_score": 0,
            "contrast_score": 0,
        }

    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_h, img_w = img_rgb.shape[:2]
    total_area = img_h * img_w

    visibility_scores, placement_scores, contrast_scores = [], [], []

    for cta in detected_ctas:
        tl = cta["coordinates"]["top_left"]
        br = cta["coordinates"]["bottom_right"]
        x1, y1 = max(0, tl[0]), max(0, tl[1])
        x2, y2 = min(img_w, br[0]), min(img_h, br[1])

        if x2 <= x1 or y2 <= y1:
            continue

        # Visibility: how much of the image the CTA occupies (scaled to 0-100)
        cta_area = (x2 - x1) * (y2 - y1)
        visibility = min(round((cta_area / total_area) * 5000, 0), 100)  # 2% of poster = 100
        visibility_scores.append(visibility)

        # Placement: bottom 33% of poster is ideal for CTA
        center_y = (y1 + y2) / 2
        if center_y > img_h * 0.66:
            placement_scores.append(100)
        elif center_y > img_h * 0.33:
            placement_scores.append(60)
        else:
            placement_scores.append(30)

        # Contrast: sample CTA region and compare to background
        region = img_rgb[y1:y2, x1:x2].reshape(-1, 3)
        if len(region) > 0:
            avg_cta_color = np.median(region, axis=0).astype(int).tolist()
            cr = calculate_contrast_ratio(avg_cta_color, background_color["rgb"])
            _, cs = wcag_grade(cr)
            contrast_scores.append(cs)

    def safe_avg(lst):
        return round(sum(lst) / len(lst), 0) if lst else 0

    return {
        "cta_found": True,
        "cta_count": len(detected_ctas),
        "visibility_score": safe_avg(visibility_scores),
        "placement_score": safe_avg(placement_scores),
        "contrast_score": safe_avg(contrast_scores),
    }


# =====================================================================
# 🌐 STEP 8 — PLATFORM SUITABILITY SCORES (for the Radar Chart)
# Scores how suitable the poster design is for 5 platforms.
# Based on: contrast, text density, color count, image quality.
# =====================================================================
def calculate_platform_suitability(text_density_pct, readability_scores, dominant_colors, cta_data):
    """
    Estimates suitability scores (0–100) for 5 platforms.

    Logic:
    - Instagram: needs high visual impact, low text density, strong colors
    - Facebook:  tolerates more text, needs good contrast
    - Print Banner: needs very high contrast + bold design
    - Web/Digital: standard readability + CTA visibility
    - Mobile:    penalizes high text density and low contrast heavily
    """
    contrast = readability_scores.get("contrast_quality", 50)
    image_q  = readability_scores.get("image_quality", 50)
    text_r   = readability_scores.get("text_readability", 50)
    cta_vis  = cta_data.get("visibility_score", 0) if cta_data.get("cta_found") else 0

    # Text density penalty: >50% text = cluttered
    clutter_penalty = max(0, text_density_pct - 30) * 1.5  # 0 to ~105 (capped)
    clutter_penalty = min(clutter_penalty, 50)

    color_variety = min(len(dominant_colors) * 10, 40)  # More colors = more visual richness

    scores = {
        "Instagram":    round(min(100, (image_q * 0.4 + contrast * 0.3 + color_variety * 0.3) - clutter_penalty * 0.8), 0),
        "Facebook":     round(min(100, (contrast * 0.4 + text_r * 0.3 + image_q * 0.3) - clutter_penalty * 0.5), 0),
        "Print Banner": round(min(100, (contrast * 0.5 + image_q * 0.3 + cta_vis * 0.2) - clutter_penalty * 0.3), 0),
        "Web / Digital":round(min(100, (text_r * 0.35 + cta_vis * 0.35 + contrast * 0.3) - clutter_penalty * 0.4), 0),
        "Mobile":       round(min(100, (contrast * 0.45 + text_r * 0.35 + image_q * 0.2) - clutter_penalty * 1.0), 0),
    }

    # Floor scores at 0
    return {k: max(0, v) for k, v in scores.items()}


# =====================================================================
# 🚀 MAIN FUNCTION — compile_color_data()
# Called by quality_assessment.py (or Colab) after M2 hands off OCR payload.
# Returns the YAML block string for Member 4.
# =====================================================================
def compile_color_data(image_path, ocr_payload, blur_score=500.0, brightness=150.0):
    """
    Full Member 3 pipeline. Takes the image path + M2's OCR payload.
    Returns:
        yaml_block (str):  YAML string to pass to Member 4
        color_data (dict): raw dict (useful for local testing/debugging)
    
    Args:
        image_path   (str):   path to the poster image
        ocr_payload  (dict):  the full dict returned by M2's extract_poster_text_and_coordinates()
        blur_score   (float): laplacian variance from M1's check_image_quality()
        brightness   (float): mean brightness from M1's check_image_quality()
    """
    print("[M3] Starting color analysis pipeline...")

    spatial_manifest = ocr_payload.get("extracted_content", {}).get("complete_spatial_manifest", [])
    detected_ctas    = ocr_payload.get("extracted_content", {}).get("detected_call_to_actions", [])
    headline         = ocr_payload.get("extracted_content", {}).get("headline", "N/A")
    cta_count        = len(detected_ctas)

    # --- Run all analysis steps ---
    dominant_colors  = extract_dominant_colors(image_path, n_colors=5)
    background_color = detect_background_color(image_path)
    text_colors      = sample_text_colors(image_path, spatial_manifest)
    text_density_pct, visual_area_pct = calculate_text_density(image_path, spatial_manifest)
    readability      = calculate_readability_scores(image_path, dominant_colors, background_color, blur_score, brightness)
    cta_analysis     = analyze_cta_visuals(image_path, detected_ctas, background_color)
    platform_scores  = calculate_platform_suitability(text_density_pct, readability, dominant_colors, cta_analysis)

    # Fill in layout clarity now that we have text density
    layout_clarity = round(max(0, 100 - text_density_pct * 1.5), 0)
    readability["layout_clarity"] = layout_clarity

    # Overall campaign score (weighted average of key metrics)
    overall_score = round((
        readability["text_readability"] * 0.25 +
        readability["contrast_quality"] * 0.25 +
        readability["image_quality"]    * 0.20 +
        layout_clarity                  * 0.15 +
        (cta_analysis["visibility_score"] if cta_analysis["cta_found"] else 0) * 0.15
    ), 0)

    # --- Assemble color_data dict (human-readable structure) ---
    color_data = {
        "overall_campaign_score": overall_score,
        "background_color": background_color,
        "dominant_colors": dominant_colors,
        "text_color_samples": text_colors,
        "readability_scores": {
            "text_readability":  readability["text_readability"],
            "contrast_quality":  readability["contrast_quality"],
            "image_quality":     readability["image_quality"],
            "layout_clarity":    readability["layout_clarity"],
            "best_contrast_ratio": readability["_best_contrast_ratio"],
            "wcag_grade":        readability["_wcag_grade"],
        },
        "text_density": {
            "text_area_percent":   text_density_pct,
            "visual_area_percent": visual_area_pct,
        },
        "cta_analysis": cta_analysis,
        "platform_suitability": platform_scores,
    }

    # --- Build YAML block for Member 4 ---
    yaml_payload = {
        "audit_input": {
            "headline":    headline,
            "cta_count":   cta_count,
            "cta_texts":   [c["text"] for c in detected_ctas],
            "total_text_regions": ocr_payload.get("metadata", {}).get("total_text_regions_found", 0),
            "cursive_warning": ocr_payload.get("metadata", {}).get("cursive_font_warning_flag", False),
        },
        "color_analysis": {
            "background_hex": background_color["hex"],
            "dominant_colors": [
                {"hex": c["hex"], "percentage": c["percentage"]}
                for c in dominant_colors
            ],
        },
        "readability_scores": {
            "text_readability":    int(readability["text_readability"]),
            "contrast_quality":    int(readability["contrast_quality"]),
            "image_quality":       int(readability["image_quality"]),
            "layout_clarity":      int(layout_clarity),
            "best_contrast_ratio": readability["_best_contrast_ratio"],
            "wcag_grade":          readability["_wcag_grade"],
        },
        "text_density": {
            "text_percent":   text_density_pct,
            "visual_percent": visual_area_pct,
        },
        "cta_effectiveness": {
            "found":            cta_analysis["cta_found"],
            "count":            cta_analysis["cta_count"],
            "visibility_score": int(cta_analysis["visibility_score"]),
            "placement_score":  int(cta_analysis["placement_score"]),
            "contrast_score":   int(cta_analysis["contrast_score"]),
        },
        "platform_suitability": {k: int(v) for k, v in platform_scores.items()},
        "overall_campaign_score": int(overall_score),
    }

    yaml_block = yaml.dump(yaml_payload, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print("[M3] ✅ Color analysis complete. YAML block ready for Member 4.")
    return yaml_block, color_data