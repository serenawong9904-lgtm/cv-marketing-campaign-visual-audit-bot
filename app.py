# -*- coding: utf-8 -*-
"""
📊 Marketing Campaign Visual Audit Bot
Telegram bot that analyses poster images and delivers a full campaign audit report with an HTML dashboard.
"""

import os
import re
import json
import cv2
import telebot
from spellchecker import SpellChecker
from pathlib import Path
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from color_layout_analysis import compile_color_data

# ── Hermes Skill (AI report generator) ───────────────────────────────
HERMES_SAMPLE_HEALTH = "Not tested"
HERMES_KEY_AVAILABLE = False
try:
    from hermes_skill.skill import member3_compile_report, OPENROUTER_KEY_AVAILABLE
    HERMES_SKILL_AVAILABLE = True
    HERMES_KEY_AVAILABLE = OPENROUTER_KEY_AVAILABLE
except ImportError:
    HERMES_SKILL_AVAILABLE = False
    print("⚠️ hermes_skill.skill unavailable; falling back to local report generation.")

try:
    import easyocr
except ImportError:
    os.system('pip install easyocr')
    import easyocr


# =====================================================================
# 📋 LOAD ASSETS FROM hermes_skill FOLDER
# =====================================================================
def load_hermes_skill_assets():
    hermes_path = Path(__file__).parent / "hermes_skill"
    with open(hermes_path / "messages.yaml", "r", encoding="utf-8") as f:
        messages = yaml.safe_load(f)
    with open(hermes_path / "markdown_template.md", "r", encoding="utf-8") as f:
        markdown_template = f.read()
    with open(hermes_path / "sample_input.yaml", "r", encoding="utf-8") as f:
        sample_input = yaml.safe_load(f)
    return messages, markdown_template, sample_input

MESSAGES, MARKDOWN_TEMPLATE, HERMES_SAMPLE_INPUT = load_hermes_skill_assets()


# =====================================================================
# 🔬 MEMBER 1: GATEKEEPER — Image Quality Assessment
# =====================================================================
def check_image_quality(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False, "Could not read the image file properly."
    laplacian_var   = cv2.Laplacian(img, cv2.CV_64F).var()
    mean_brightness = img.mean()
    if mean_brightness < 40.0:
        return False, f"Image is too dark (Brightness: {round(mean_brightness, 1)}/255)."
    if laplacian_var < 300.0:
        return False, f"Image is too blurry (Blur Score: {round(laplacian_var, 1)})."
    return True, (laplacian_var, mean_brightness)


# =====================================================================
# 🧠 MEMBER 2: TEXT SPECIALIST — OCR + Headline + CTA + Spatial Map
# =====================================================================
def extract_poster_text_and_coordinates(image_path="user_poster.jpg"):
    print(f"Initializing EasyOCR pipeline for: {image_path}")
    reader  = easyocr.Reader(['en'], gpu=False)
    results = reader.readtext(image_path)

    if not results:
        return {"status": "error", "message": "No text detected in the image."}

    spell = SpellChecker()
    all_extracted_elements = []
    headline_text     = ""
    max_bounding_area = 0
    low_confidence_counter = 0
    typo_list         = []

    cta_patterns = [
        r"join\s*now", r"register\s*now", r"scan\s*here", r"scan\s*me",
        r"apply\s*now", r"book\s*now", r"rsvp", r"buy\s*now", r"order\s*now",
        r"click\s*here", r"visit\s*us", r"get\s*yours", r"limited\s*offer",
        r"bridge\s*the\s*gap", r"cloud\s*run"
    ]
    cta_regex    = re.compile("|".join(cta_patterns), re.IGNORECASE)
    detected_ctas = []

    for (bbox, text, confidence) in results:
        top_left     = [int(bbox[0][0]), int(bbox[0][1])]
        bottom_right = [int(bbox[2][0]), int(bbox[2][1])]
        raw_text     = text.strip()

        words = raw_text.split()
        processed_words = []
        for word in words:
            clean_word = re.sub(r'[^\w\s&]', '', word)

            if re.match(r'^\d+[tsrd]$', clean_word.lower()):
                suffix_map = {'t': 'th', 's': 'st', 'n': 'nd', 'r': 'rd'}
                last_char  = clean_word.lower()[-1]
                if last_char in suffix_map:
                    word = word + suffix_map[last_char][1:]
                processed_words.append(word)
                continue

            if (clean_word == "&" or clean_word.isdigit() or clean_word.isupper()
                    or any(char.isdigit() for char in clean_word) or confidence >= 0.85):
                if any(char.isdigit() for char in word):
                    word = word.replace('O', '0').replace('o', '0')
                processed_words.append(word)
                continue

            if clean_word.lower() not in spell:
                correction = spell.correction(clean_word)
                if correction and correction != clean_word:
                    typo_list.append(f'"{clean_word}" -> "{correction}"')
                    adjusted_case = (
                        correction.upper()      if word.isupper()     else
                        correction.capitalize() if word[0].isupper()  else
                        correction
                    )
                    processed_words.append(adjusted_case)
                    continue

            processed_words.append(word)

        cleaned_text = " ".join(processed_words)
        cleaned_text = re.sub(r'(?i)(\d+)[.・:](\d+)\s*(am|pm)', r'\1:\2\3', cleaned_text)

        width  = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        current_area = width * height

        if confidence < 0.65:
            low_confidence_counter += 1

        element_entry = {
            "text": cleaned_text,
            "raw_ocr_original": raw_text if raw_text != cleaned_text else "No Correction Needed",
            "confidence": float(round(confidence, 3)),
            "bounding_box": {"top_left": top_left, "bottom_right": bottom_right}
        }
        all_extracted_elements.append(element_entry)

        if current_area > max_bounding_area and len(cleaned_text) > 3:
            if not any(ext in cleaned_text.lower() for ext in ["preview", ".jpg", ".png", ".jpeg"]):
                max_bounding_area = current_area
                headline_text     = cleaned_text

        if cta_regex.search(cleaned_text):
            # Coordinates stored as dict so analyze_cta_visuals() can read top_left/bottom_right.
            # coordinates_str is used for display only.
            detected_ctas.append({
                "text": cleaned_text,
                "type": "textual_intent",
                "coordinates": {"top_left": top_left, "bottom_right": bottom_right},
                "coordinates_str": f"[x: {top_left[0]}, y: {top_left[1]}]"
            })

    total_regions       = len(all_extracted_elements)
    has_cursive_anomaly = (low_confidence_counter / total_regions) > 0.15 if total_regions > 0 else False

    return {
        "status": "success",
        "metadata": {
            "total_text_regions_found":    total_regions,
            "low_confidence_text_regions": low_confidence_counter,
            "cursive_font_warning_flag":   has_cursive_anomaly
        },
        "extracted_content": {
            "headline":                  headline_text if headline_text else "None Detected Confidently",
            "detected_call_to_actions":  detected_ctas,
            "raw_text_stream":           [item["text"] for item in all_extracted_elements],
            "typos_found":               typo_list,
            "complete_spatial_manifest": all_extracted_elements  # Required by color_layout_analysis
        }
    }


# ─────────────────────────────────────────────────────────────────────
# Helpers: extract sections from the AI audit report markdown
# ─────────────────────────────────────────────────────────────────────
def extract_chart_metrics_from_report(audit_report):
    try:
        # Try code fence first (AI output wraps JSON in ```json ... ```)
        json_match = re.search(r'```json\s*(.*?)\s*```', audit_report, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
            if 'metrics' in parsed:
                return parsed['metrics']
        # Fallback: locate the JSON object by finding "chart_type" key
        idx = audit_report.find('"chart_type"')
        if idx != -1:
            start = audit_report.rfind('{', 0, idx)
            if start != -1:
                decoder = json.JSONDecoder()
                parsed, _ = decoder.raw_decode(audit_report[start:])
                if 'metrics' in parsed:
                    return parsed['metrics']
    except Exception as e:
        print(f"⚠️ Could not extract chart metrics from report: {e}")
    return None


def extract_report_section(audit_report, keywords):
    if not isinstance(audit_report, str) or not audit_report.strip():
        return ""
    for keyword in keywords:
        pattern = rf'^#{2,}\s*[^\n]*\b{re.escape(keyword)}\b[^\n]*\n(.*?)(?:\n^#{{2,}}\s|\Z)'
        match   = re.search(pattern, audit_report, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if match:
            section = match.group(1).strip()
            section = re.sub(r'^\s*[-*] ?', '', section, flags=re.MULTILINE)
            section = re.sub(r'\n{2,}', '\n\n', section)
            return section.strip()
    return ""


def extract_cta_section_from_report(audit_report):
    return extract_report_section(audit_report, [
        'CTA Analysis', 'Call-to-Action (CTA) Analysis',
        'Call to Action Analysis', 'CTA Summary'
    ])


def extract_ai_recommendations_from_report(audit_report):
    raw_section = extract_report_section(audit_report, [
        'Improvement Suggestions', 'Strategic Recommendations',
        'Recommendations', 'Improvement Recommendations'
    ])
    if not raw_section:
        return []
    lines = []
    for raw_line in raw_section.splitlines():
        cleaned = raw_line.strip().lstrip('-* ').strip()
        if cleaned:
            lines.append(cleaned)
    return lines


# =====================================================================
# 🧾 MEMBER 3 (LOCAL FALLBACK): Fill Markdown Template
# =====================================================================
def fill_markdown_template(ocr_data, metrics):
    readability_score = 85 if not ocr_data['metadata']['cursive_font_warning_flag'] else 65
    ctas_list         = ocr_data['extracted_content']['detected_call_to_actions']
    cta_score         = 10 if ctas_list else 0
    visual_impact     = 80 if metrics['blur_score'] > 500 else 60
    total_regions     = ocr_data['metadata']['total_text_regions_found']
    info_clarity      = 75 if total_regions < 15 else 55

    if total_regions > 18:
        recommended_platform = "Print Media / Flyer"
        platform_reasoning   = "High text density suits detailed print layouts."
    else:
        recommended_platform = "Social Media Feed / Web Ads"
        platform_reasoning   = "Lower text density fits fast-scroll digital consumption."

    cta_text          = ", ".join([c['text'] for c in ctas_list]) if ctas_list else "None Detected"
    cta_suffix        = 's' if len(ctas_list) != 1 else ''
    cta_presence_text = (f"with {len(ctas_list)} detected CTA{cta_suffix}."
                         if ctas_list else "with no clear call-to-action.")
    cursive_comment   = ("Cursive fonts detected — may impact mobile readability."
                         if ocr_data['metadata']['cursive_font_warning_flag']
                         else "Clean typography detected with good readability.")

    if total_regions > 20:
        layout_comment = "CLUTTERED — Too many text regions may cause cognitive overload."
    elif total_regions > 12:
        layout_comment = "MODERATELY DENSE — Good volume, could be optimised for faster scans."
    else:
        layout_comment = "WELL-SPACED — Clean layout with optimal information hierarchy."

    report = MARKDOWN_TEMPLATE.replace(
        "[Provide a 2-3 sentence summary evaluating the overall poster design based on text regions and CTAs.]",
        f"This marketing poster presents {total_regions} text regions {cta_presence_text} "
        f"The layout achieves a {'strong' if total_regions < 15 else 'moderate'} information hierarchy. "
        f"Overall strategic grade: {'A' if cta_score > 5 and total_regions < 15 else 'B'}"
    ).replace("[Number of text regions]", str(total_regions)
    ).replace("[Comment on cursive font warnings or readability]", cursive_comment
    ).replace("[Is it too cluttered or well-spaced?]", layout_comment
    ).replace("[List of CTAs]", cta_text
    ).replace("[X]/10", f"{cta_score}/10"
    ).replace("[Why the CTA is strong, weak, or missing]",
              "Strong CTA placement detected." if cta_score > 5
              else "No clear CTA found; add a stronger action trigger."
    ).replace("[Actionable suggestion 1]",
              "Optimise text density: consolidate regions into a clear visual hierarchy"
              if total_regions > 15 else "Maintain clean layout structure"
    ).replace("[Actionable suggestion 2]",
              "Enhance CTA visibility: use contrasting colours and bold fonts"
              if cta_score < 5 else "CTA placement is optimal — maintain current strategy"
    ).replace("[Actionable suggestion 3]",
              "Replace cursive fonts with geometric typography for mobile"
              if ocr_data['metadata']['cursive_font_warning_flag']
              else "Font selection supports platform versatility"
    ).replace("[Instagram / Facebook / Print / etc.]", recommended_platform
    ).replace("[Why this layout/text density fits the platform]", platform_reasoning)

    chart_blueprint = json.dumps({
        "chart_type": "radar",
        "metrics": {
            "Readability":        readability_score,
            "CTA_Strength":       cta_score * 10,
            "Visual_Impact":      visual_impact,
            "Information_Clarity": info_clarity
        }
    }, indent=2)

    report = report.replace(
        '{\n  "chart_type": "radar",\n  "metrics": {\n    "Readability": 85,\n'
        '    "CTA_Strength": 90,\n    "Visual_Impact": 75,\n    "Information_Clarity": 80\n  }\n}',
        chart_blueprint
    )
    return report


def generate_audit_report(ocr_data, metrics):
    """Use Hermes Skill when available; fall back to local markdown template."""
    payload = {
        "metadata":         ocr_data["metadata"],
        "extracted_content": ocr_data["extracted_content"],
        "quality_metrics": {
            "blur_score":       metrics["blur_score"],
            "brightness_score": metrics["brightness_score"]
        }
    }
    if HERMES_SKILL_AVAILABLE:
        if not HERMES_KEY_AVAILABLE:
            print("⚠️ OpenRouter key missing — falling back to local report.")
            return fill_markdown_template(ocr_data, metrics)
        try:
            report = member3_compile_report(payload)
            if isinstance(report, str) and report.startswith("❌"):
                return fill_markdown_template(ocr_data, metrics)
            if not report or not report.strip():
                return fill_markdown_template(ocr_data, metrics)
            return report
        except Exception as e:
            print(f"⚠️ Hermes Skill failed: {e}")
            return fill_markdown_template(ocr_data, metrics)
    return fill_markdown_template(ocr_data, metrics)


def run_hermes_skill_sample_test():
    global HERMES_SAMPLE_HEALTH
    if not HERMES_SKILL_AVAILABLE:
        HERMES_SAMPLE_HEALTH = "Hermes Skill unavailable; fallback report generation active."
        print(f"ℹ️ {HERMES_SAMPLE_HEALTH}")
        return
    try:
        sample_report = member3_compile_report(HERMES_SAMPLE_INPUT)
        if sample_report and not sample_report.startswith("❌"):
            HERMES_SAMPLE_HEALTH = "Hermes Skill sample payload executed successfully."
        else:
            HERMES_SAMPLE_HEALTH = "Hermes Skill returned a fallback or error response."
    except Exception as e:
        HERMES_SAMPLE_HEALTH = f"Hermes Skill sample test failed: {e}"
    print(f"ℹ️ {HERMES_SAMPLE_HEALTH}")


# =====================================================================
# 🧱 MEMBER 5: THE BUILDER — HTML Dashboard
# =====================================================================
def build_dashboard_html(blueprint_data, report_text_log, html_filename="dashboard.html"):
    """Build the HTML dashboard from pipeline outputs and AI report."""

    # ── Parse AI report into sections ────────────────────────────────
    def _sec(keywords):
        return extract_report_section(report_text_log, keywords)

    readability_sec = _sec(['Readability', 'Visual Quality'])
    cta_sec         = _sec(['CTA Analysis', 'Call-to-Action (CTA) Analysis', 'Call to Action Analysis'])
    platform_sec    = _sec(['Platform Suitability'])
    suggestions = extract_ai_recommendations_from_report(report_text_log)
    if not suggestions:
        suggestions = (blueprint_data.get('ai_recommendations') or
                       blueprint_data.get('suggestions') or [])

    chart_metrics = extract_chart_metrics_from_report(report_text_log) or {}
    if not chart_metrics:
        try:
            bp_str    = blueprint_data.get('chart_blueprint', '{}')
            bp_parsed = json.loads(bp_str) if isinstance(bp_str, str) else bp_str
            chart_metrics = bp_parsed.get('metrics', {})
        except Exception:
            chart_metrics = {}

    # ── Pipeline data ─────────────────────────────────────────────────
    cta_found         = blueprint_data.get('cta_found', False)
    cta_texts         = blueprint_data.get('cta_texts', [])
    cta_score_display = blueprint_data.get('cta_score_display', 'N/A')
    cta_coords        = blueprint_data.get('cta_coords', 'None Detected')
    overall_grade     = blueprint_data.get('overall_grade', 'N/A')
    blur_val          = blueprint_data.get('m1_blur_val', 'N/A')
    brightness_val    = blueprint_data.get('m1_brightness', 'N/A')
    total_regions     = blueprint_data.get('m2_total_words', 'N/A')
    cursive_flag      = blueprint_data.get('m2_cursive_flag', False)
    cta_phrases       = ', '.join(cta_texts) if cta_texts else 'None Detected'

    color_data           = blueprint_data.get('color_data', {})
    dominant_colors      = color_data.get('dominant_colors', [])
    background_color     = color_data.get('background_color', {})
    overall_score        = color_data.get('overall_campaign_score', 'N/A')
    platform_suitability = color_data.get('platform_suitability', {})
    readability_scores   = color_data.get('readability_scores', {})
    text_density         = color_data.get('text_density', {})

    # ── Score ring ────────────────────────────────────────────────────
    try:
        score_pct   = int(float(overall_score))
        score_color = '#059669' if score_pct >= 70 else '#D97706' if score_pct >= 50 else '#DC2626'
        ring_bg     = f'conic-gradient({score_color} {score_pct}%, #E5E7EB 0%)'
    except Exception:
        score_pct   = 0
        score_color = '#6366F1'
        ring_bg     = 'conic-gradient(#6366F1 0%, #E5E7EB 0%)'

    # ── CTA vars ──────────────────────────────────────────────────────
    cta_icon       = '✅' if cta_found else '❌'
    cta_label      = 'Found' if cta_found else 'Missing'
    cta_badge_cls  = 'cta-found' if cta_found else 'cta-missing'
    cta_num_cls    = 'badge-green' if cta_found else 'badge-red'
    cursive_cls    = 'tag-amber' if cursive_flag else 'tag-green'
    cursive_txt    = 'Detected' if cursive_flag else 'Clean'

    # ── Render a markdown section as HTML ─────────────────────────────
    def _render(text):
        if not text:
            return ''
        rows = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                rows.append('<div style="height:6px;"></div>')
                continue
            s = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
            if s.startswith('- ') or s.startswith('* '):
                rows.append(f'<div class="rli">{s[2:]}</div>')
            else:
                rows.append(f'<div class="rp">{s}</div>')
        return '\n'.join(rows)

    # ── Render full report (with heading detection) ───────────────────
    def _render_full(text):
        rows = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                rows.append('<div style="height:8px;"></div>')
                continue
            if s.startswith('```'):
                continue
            s2 = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
            if s.startswith('### '):
                rows.append(f'<div class="rh3">{s[4:]}</div>')
            elif s.startswith('## '):
                rows.append(f'<div class="rh2">{s[3:]}</div>')
            elif s.startswith('# '):
                rows.append(f'<div class="rh1">{s[2:]}</div>')
            elif s.startswith('- ') or s.startswith('* '):
                rows.append(f'<div class="rli">{s2[2:]}</div>')
            else:
                rows.append(f'<div class="rp">{s2}</div>')
        return '\n'.join(rows)

    report_html      = _render_full(report_text_log)
    readability_html = _render(readability_sec)
    cta_html        = _render(cta_sec)
    platform_html   = _render(platform_sec)

    # ── Chart metric bars ────────────────────────────────────────────
    metric_styles = {
        'Readability':         ('linear-gradient(90deg,#6366F1,#818CF8)', '#EDE9FE'),
        'CTA_Strength':        ('linear-gradient(90deg,#10B981,#34D399)', '#ECFDF5'),
        'Visual_Impact':       ('linear-gradient(90deg,#F59E0B,#FCD34D)', '#FEF3C7'),
        'Information_Clarity': ('linear-gradient(90deg,#3B82F6,#60A5FA)', '#DBEAFE'),
    }
    chart_bars = ''
    if chart_metrics:
        for key, val in chart_metrics.items():
            pct   = max(0, min(int(round(float(val))), 100))
            label = key.replace('_', ' ').title()
            grad, track = metric_styles.get(key, ('linear-gradient(90deg,#6366F1,#818CF8)', '#EDE9FE'))
            chart_bars += f"""<div class="mrow">
  <div class="mhdr"><span class="mname">{label}</span><span class="mscore">{pct}/100</span></div>
  <div class="btrack" style="background:{track};"><div class="bfill" style="width:{pct}%;background:{grad};"></div></div>
</div>"""
    else:
        chart_bars = ''

    # ── Readability bars ──────────────────────────────────────────────
    read_bars = ''
    for label, key, grad in [
        ('Text Readability',  'text_readability',  'linear-gradient(90deg,#8B5CF6,#A78BFA)'),
        ('Contrast Quality',  'contrast_quality',  'linear-gradient(90deg,#3B82F6,#60A5FA)'),
        ('Image Quality',     'image_quality',     'linear-gradient(90deg,#10B981,#34D399)'),
        ('Layout Clarity',    'layout_clarity',    'linear-gradient(90deg,#F59E0B,#FCD34D)'),
    ]:
        score = int(round(float(readability_scores.get(key, 0) or 0)))
        pct   = max(0, min(score, 100))
        grade = '🟢' if pct >= 80 else '🟡' if pct >= 60 else '🔴'
        read_bars += f"""<div class="mrow">
  <div class="mhdr"><span class="mname">{label}</span>
    <span style="display:flex;gap:6px;align-items:center;"><span class="mscore">{pct}/100</span><span style="font-size:.75rem;">{grade}</span></span>
  </div>
  <div class="btrack"><div class="bfill" style="width:{pct}%;background:{grad};"></div></div>
</div>"""

    # ── Platform suitability bars ─────────────────────────────────────
    pal = ['#E1306C', '#1877F2', '#059669', '#6366F1', '#F59E0B']
    if platform_suitability:
        plats = [(k, int(v)) for k, v in platform_suitability.items()]
    else:
        plats = [
            ('Instagram Stories', int(blueprint_data.get('suit_insta', 0.88) * 100)),
            ('Web Display',       int(blueprint_data.get('suit_web',   0.78) * 100)),
            ('Print Media',       int(blueprint_data.get('suit_print', 0.50) * 100)),
        ]
    plat_bars = ''
    for i, (name, score) in enumerate(plats):
        plat_bars += f"""<div class="platrow">
  <span class="platname">{name}</span>
  <div class="btrack" style="height:10px;"><div class="bfill" style="width:{score}%;background:{pal[i % len(pal)]};"></div></div>
  <span class="platpct">{score}%</span>
</div>"""

    # ── Color swatches ────────────────────────────────────────────────
    swatches = ''
    if dominant_colors:
        swatches = '<div class="swatches">'
        for c in dominant_colors[:5]:
            swatches += (f'<div class="sw-item"><div class="sw-box" style="background:{c.get("hex","#000")};"></div>'
                         f'<span class="sw-hex">{c.get("hex","N/A")}</span>'
                         f'<span class="sw-pct">{c.get("percentage",0)}%</span></div>')
        swatches += '</div>'

    bg_hex  = background_color.get('hex', '#000000')
    bg_chip = (f'<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;'
               f'background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;">'
               f'<span style="width:16px;height:16px;background:{bg_hex};border-radius:3px;border:1px solid #E2E8F0;display:inline-block;"></span>'
               f'<span style="font-size:.82rem;font-weight:700;font-family:monospace;color:#374151;">{bg_hex}</span></span>')

    # ── Text density bars ─────────────────────────────────────────────
    t_pct   = float(text_density.get('text_area_percent', 0) or 0)
    v_pct   = float(text_density.get('visual_area_percent', 0) or 0)
    density = ''
    if t_pct or v_pct:
        density = f"""<div style="margin-top:14px;">
  <div class="dlabel"><span>Text Coverage</span><span>{t_pct}%</span></div>
  <div class="btrack"><div class="bfill" style="width:{t_pct}%;background:linear-gradient(90deg,#F43F5E,#FB7185);"></div></div>
  <div class="dlabel" style="margin-top:10px;"><span>Visual Space</span><span>{v_pct}%</span></div>
  <div class="btrack"><div class="bfill" style="width:{v_pct}%;background:linear-gradient(90deg,#10B981,#34D399);"></div></div>
</div>"""

    # ── Suggestion cards ──────────────────────────────────────────────
    recs_html = ''
    if suggestions:
        for i, rec in enumerate(suggestions[:5], 1):
            recs_html += f'<div class="rec"><div class="rec-n">{i}</div><div class="rec-t">{rec}</div></div>'
    else:
        recs_html = ''

    # ── CSS (plain string — real braces, no escaping needed) ──────────
    css = """<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;background:#F1F5F9;color:#0F172A;line-height:1.6;min-height:100vh;}
.page{max-width:1380px;margin:0 auto;padding:24px;}
/* Hero */
.hero{background:linear-gradient(135deg,#1E40AF 0%,#7C3AED 55%,#DB2777 100%);border-radius:24px;padding:40px 44px;color:#fff;margin-bottom:20px;}
.hero h1{font-size:1.85rem;font-weight:800;margin-bottom:6px;letter-spacing:-.02em;}
.hero p{opacity:.85;font-size:.95rem;}
/* Stats bar */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px;}
.stat{background:#fff;border-radius:16px;padding:18px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 12px rgba(0,0,0,.04);border:1px solid #E2E8F0;text-align:center;}
.slbl{font-size:.7rem;color:#64748B;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px;}
.sval{font-size:1.5rem;font-weight:800;color:#0F172A;}
.ssub{font-size:.76rem;color:#94A3B8;margin-top:3px;}
/* Grid layouts */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}
.g60{display:grid;grid-template-columns:1.6fr 1fr;gap:20px;margin-bottom:20px;}
.g1{margin-bottom:20px;}
/* Cards */
.card{background:#fff;border-radius:20px;padding:26px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.04);border:1px solid #E2E8F0;}
/* Section badge */
.sbadge{display:flex;align-items:center;gap:10px;margin-bottom:18px;}
.bnum{width:30px;height:30px;border-radius:50%;font-weight:800;font-size:.82rem;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.badge-blue{background:#DBEAFE;color:#1D4ED8;}
.badge-purple{background:#EDE9FE;color:#5B21B6;}
.badge-green{background:#DCFCE7;color:#166534;}
.badge-red{background:#FEE2E2;color:#991B1B;}
.badge-amber{background:#FEF3C7;color:#92400E;}
.badge-indigo{background:#E0E7FF;color:#3730A3;}
.stitle{font-size:1rem;font-weight:700;color:#0F172A;}
/* Score ring */
.sring-wrap{display:flex;flex-direction:column;align-items:center;padding:22px;background:#F8FAFC;border-radius:16px;border:1px solid #E2E8F0;margin-bottom:14px;}
.sring{width:100px;height:100px;border-radius:50%;display:flex;align-items:center;justify-content:center;position:relative;}
.sring-in{position:absolute;width:72px;height:72px;background:#fff;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;}
.snum{font-size:1.4rem;font-weight:800;line-height:1;}
.sden{font-size:.63rem;color:#94A3B8;}
/* CTA badge */
.cta-badge{display:inline-flex;align-items:center;gap:10px;padding:12px 20px;border-radius:999px;font-weight:700;font-size:1rem;margin-bottom:16px;}
.cta-found{background:#ECFDF5;color:#065F46;border:1.5px solid #6EE7B7;}
.cta-missing{background:#FEF2F2;color:#991B1B;border:1.5px solid #FCA5A5;}
/* Info rows */
.ir{display:flex;align-items:flex-start;gap:8px;margin-bottom:9px;font-size:.88rem;}
.il{color:#94A3B8;font-weight:600;min-width:115px;flex-shrink:0;}
.iv{color:#0F172A;font-weight:600;}
.tag{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:700;}
.tag-green{background:#DCFCE7;color:#166534;}
.tag-amber{background:#FEF3C7;color:#92400E;}
/* Metric bars */
.mrow{margin-bottom:14px;}.mrow:last-child{margin-bottom:0;}
.mhdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;}
.mname{font-size:.88rem;font-weight:600;color:#374151;}
.mscore{font-size:.84rem;font-weight:700;color:#0F172A;}
.btrack{height:9px;background:#F1F5F9;border-radius:999px;overflow:hidden;}
.bfill{height:100%;border-radius:999px;}
/* Platform */
.platrow{display:grid;grid-template-columns:155px 1fr 50px;align-items:center;gap:12px;margin-bottom:12px;}
.platrow:last-child{margin-bottom:0;}
.platname{font-size:.88rem;font-weight:600;color:#374151;}
.platpct{font-size:.88rem;font-weight:700;color:#0F172A;text-align:right;}
/* Recs */
.rec{display:flex;align-items:flex-start;gap:14px;padding:14px 16px;background:#F8FAFC;border-radius:14px;border:1px solid #E2E8F0;margin-bottom:10px;}
.rec:last-child{margin-bottom:0;}
.rec-n{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#6366F1,#8B5CF6);color:#fff;font-weight:800;font-size:.82rem;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}
.rec-t{font-size:.88rem;color:#374151;font-weight:500;line-height:1.6;}
/* Swatches */
.swatches{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.sw-item{text-align:center;}
.sw-box{width:54px;height:54px;border-radius:12px;border:2px solid rgba(0,0,0,.06);box-shadow:0 2px 8px rgba(0,0,0,.08);}
.sw-hex{display:block;font-size:.7rem;font-weight:700;color:#374151;margin-top:5px;font-family:monospace;}
.sw-pct{display:block;font-size:.66rem;color:#94A3B8;}
/* Density */
.dlabel{display:flex;justify-content:space-between;font-size:.84rem;font-weight:600;color:#374151;margin-bottom:5px;}
/* Report rendering */
.rbox{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:14px;padding:20px;max-height:400px;overflow-y:auto;font-size:.87rem;color:#334155;}
.rh1,.rh2{font-size:1rem;font-weight:700;color:#1E3A8A;margin:14px 0 6px;padding-left:2px;}
.rh3{font-size:.9rem;font-weight:700;color:#374151;margin:10px 0 4px;}
.rh1:first-child,.rh2:first-child,.rh3:first-child{margin-top:0;}
.rli{padding-left:18px;margin-bottom:5px;position:relative;}
.rli::before{content:"•";position:absolute;left:0;color:#6366F1;font-weight:700;}
.rp{margin-bottom:5px;line-height:1.65;}
.sec-text .rp,.sec-text .rli{margin-bottom:6px;font-size:.9rem;color:#334155;line-height:1.65;}
.divider{height:1px;background:#E2E8F0;margin:18px 0;}
.sublbl{font-size:.76rem;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.07em;margin-bottom:14px;}
@media(max-width:1024px){.g2,.g60{grid-template-columns:1fr;}.stats{grid-template-columns:repeat(3,1fr);}}
@media(max-width:640px){.stats{grid-template-columns:1fr 1fr;}.page{padding:14px;}}
</style>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MCVA — Campaign Audit Dashboard</title>
{css}
</head>
<body>
<div class="page">

  <!-- ── Hero ────────────────────────────────────────────── -->
  <div class="hero">
    <h1>📊 Marketing Campaign Visual Audit Dashboard</h1>
    <p>Automated visual audit · Upload your poster to receive a full campaign analysis</p>
  </div>

  <!-- ── Quick Stats ─────────────────────────────────────── -->
  <div class="stats">
    <div class="stat">
      <div class="slbl">Overall Score</div>
      <div class="sval" style="color:{score_color};">{overall_score}</div>
      <div class="ssub">Grade: {overall_grade}</div>
    </div>
    <div class="stat">
      <div class="slbl">CTA Status</div>
      <div class="sval" style="font-size:1.7rem;">{cta_icon}</div>
      <div class="ssub">{cta_label} &nbsp;·&nbsp; {cta_score_display}</div>
    </div>
    <div class="stat">
      <div class="slbl">Text Regions</div>
      <div class="sval">{total_regions}</div>
      <div class="ssub">extracted by OCR</div>
    </div>
    <div class="stat">
      <div class="slbl">Blur Score</div>
      <div class="sval">{blur_val}</div>
      <div class="ssub">Laplacian var.</div>
    </div>
    <div class="stat">
      <div class="slbl">Brightness</div>
      <div class="sval">{brightness_val}</div>
      <div class="ssub">mean pixel / 255</div>
    </div>
  </div>

  <!-- ── 1️⃣  Audit Report ────────────────────────────────── -->
  <div class="g1">
    <div class="card">
      <div class="sbadge"><div class="bnum badge-blue">1</div><span class="stitle">Audit Report</span></div>
      <div style="display:grid;grid-template-columns:1fr 320px;gap:20px;align-items:start;">
        <div class="rbox">{report_html}</div>
        <div>
          <div class="sring-wrap">
            <div class="sring" style="background:{ring_bg};">
              <div class="sring-in">
                <span class="snum" style="color:{score_color};">{overall_score}</span>
                <span class="sden">/ 100</span>
              </div>
            </div>
            <div style="text-align:center;margin-top:12px;">
              <div style="font-size:.74rem;color:#64748B;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Campaign Score</div>
              <div style="font-size:1.1rem;font-weight:800;color:#0F172A;margin-top:3px;">Grade: {overall_grade}</div>
            </div>
          </div>
          <div style="background:#F8FAFC;border-radius:14px;border:1px solid #E2E8F0;padding:16px;">
            <div class="ir"><span class="il">Text Regions:</span><span class="iv">{total_regions}</span></div>
            <div class="ir"><span class="il">CTA Status:</span><span class="iv">{cta_icon} {cta_label}</span></div>
            <div class="ir"><span class="il">Cursive Font:</span><span class="tag {cursive_cls}">{cursive_txt}</span></div>
            <div class="ir"><span class="il">Blur Score:</span><span class="iv">{blur_val}</span></div>
            <div class="ir"><span class="il">Brightness:</span><span class="iv">{brightness_val}/255</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── 2️⃣ Readability  +  3️⃣ CTA ──────────────────────── -->
  <div class="g2">

    <div class="card">
      <div class="sbadge"><div class="bnum badge-purple">2</div><span class="stitle">Readability &amp; Visual Quality</span></div>
      <div class="sec-text">{readability_html}</div>
      <div class="divider"></div>
      <div class="sublbl">Contrast &amp; Quality Scores</div>
      {read_bars}
    </div>

    <div class="card">
      <div class="sbadge"><div class="bnum {cta_num_cls}">3</div><span class="stitle">Call-to-Action (CTA) Analysis</span></div>
      <span class="cta-badge {cta_badge_cls}">{cta_icon} CTA {cta_label}</span>
      <div class="sec-text">{cta_html}</div>
      <div class="divider"></div>
      <div class="ir"><span class="il">Detected CTAs:</span><span class="iv" style="font-size:.85rem;">{cta_phrases}</span></div>
      <div class="ir"><span class="il">CTA Score:</span><span class="iv">{cta_score_display}</span></div>
      <div class="ir"><span class="il">Location:</span><span class="iv" style="font-size:.84rem;">{cta_coords}</span></div>
    </div>

  </div>

  <!-- ── 4️⃣ Suggestions  +  Chart Metrics ─────────────────── -->
  <div class="g2">

    <div class="card">
      <div class="sbadge"><div class="bnum badge-amber">4</div><span class="stitle">AI Improvement Suggestions</span></div>
      {recs_html}
    </div>

    <div class="card">
      <div class="sbadge"><div class="bnum badge-blue">📈</div><span class="stitle">Performance Metrics Blueprint</span></div>
      <div class="sublbl">Scores from AI Audit Report</div>
      {chart_bars}
    </div>

  </div>

  <!-- ── 5️⃣  Platform Suitability ────────────────────────── -->
  <div class="g1">
    <div class="card">
      <div class="sbadge"><div class="bnum badge-indigo">5</div><span class="stitle">Platform Suitability</span></div>
      {plat_bars}
    </div>
  </div>

  <!-- ── Color Palette ────────────────────────────────────── -->
  <div class="g1">
    <div class="card">
      <div class="sublbl">🎨 Dominant Color Palette</div>
      {swatches}
      <div class="ir" style="margin-top:10px;"><span class="il">Background:</span><span>{bg_chip}</span></div>
      {density}
    </div>
  </div>

</div>
</body>
</html>"""

    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_content)


# =====================================================================
# 🤖 TELEGRAM BOT HANDLERS
# =====================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8726514152:AAGddaMY47826AEKjy143FGkPoHvfs6kyiA").strip()

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, MESSAGES['welcome_message'], parse_mode='Markdown')


@bot.message_handler(commands=['end'])
def send_end_message(message):
    bot.reply_to(message, MESSAGES['end_message'], parse_mode='Markdown')


@bot.message_handler(func=lambda _: True, content_types=['text'])
def handle_text_fallback(message):
    if message.text.strip().lower() in ('/end', '/start'):
        return
    bot.reply_to(message, MESSAGES['operational_mode'])


@bot.message_handler(content_types=['photo'])
def handle_incoming_poster(message):
    chat_id = message.chat.id
    bot.reply_to(message, "📥 Poster received! Running quality check...")

    # ── Download + quality gate ─────────────────────────────────────
    file_info        = bot.get_file(message.photo[-1].file_id)
    downloaded_file  = bot.download_file(file_info.file_path)
    local_image_path = "user_poster.jpg"
    with open(local_image_path, 'wb') as f:
        f.write(downloaded_file)

    quality_pass, quality_metrics = check_image_quality(local_image_path)
    if not quality_pass:
        bot.reply_to(message, MESSAGES['image_quality_fail'].format(reason=quality_metrics))
        return

    blur_score, brightness_score = quality_metrics
    bot.reply_to(message, MESSAGES['image_quality_pass'].format(
        blur_score=round(blur_score, 1),
        brightness_score=round(brightness_score, 1)
    ))

    # ── OCR extraction ──────────────────────────────────────────────
    ocr_result = extract_poster_text_and_coordinates(local_image_path)
    if ocr_result["status"] == "error":
        bot.send_message(chat_id, MESSAGES['pipeline_parse_fail'].format(reason=ocr_result['message']))
        return

    headline          = ocr_result['extracted_content']['headline']
    total_text_blocks = ocr_result['metadata']['total_text_regions_found']
    cursive_flag      = ocr_result['metadata']['cursive_font_warning_flag']
    ctas_list         = ocr_result['extracted_content']['detected_call_to_actions']
    typos_list        = ocr_result['extracted_content']['typos_found']

    cursive_notice = "\n⚠️ **Notice:** Cursive font families detected." if cursive_flag else ""
    bot.reply_to(message, MESSAGES['feedback_report'].format(
        headline=headline,
        cta_count=len(ctas_list),
        cursive_flag=cursive_notice
    ), parse_mode='Markdown')

    # ── Color & layout analysis ─────────────────────────────────────
    try:
        _, color_data = compile_color_data(
            local_image_path, ocr_result,
            blur_score=blur_score, brightness=brightness_score
        )
    except Exception as e:
        print(f"⚠️ Color analysis failed (non-blocking): {e}")
        color_data = None

    # ── AI audit report ─────────────────────────────────────────────
    metrics      = {'blur_score': blur_score, 'brightness_score': brightness_score}
    audit_report = generate_audit_report(ocr_result, metrics)

    # Prefer metrics extracted from AI report; fall back to local calculations
    report_metrics    = extract_chart_metrics_from_report(audit_report)
    readability_score = (report_metrics or {}).get('Readability',    85 if not cursive_flag else 65)
    cta_strength      = (report_metrics or {}).get('CTA_Strength',   10 if ctas_list else 0)
    visual_impact     = (report_metrics or {}).get('Visual_Impact',  80 if blur_score > 500 else 60)
    info_clarity      = (report_metrics or {}).get('Information_Clarity', 75 if total_text_blocks < 15 else 55)

    # Normalise CTA strength to 0–100
    if isinstance(cta_strength, (int, float)) and cta_strength <= 10:
        cta_strength = int(cta_strength * 10)
    cta_score_display = f"{int(cta_strength)}/100"

    cta_found_flag   = len(ctas_list) > 0
    cta_summary_text = extract_cta_section_from_report(audit_report) or (
        'CTAs found.' if cta_found_flag else 'No CTAs detected.'
    )
    ai_recommendations = extract_ai_recommendations_from_report(audit_report)

    # ── Build dashboard blueprint ───────────────────────────────────
    integrated_blueprint = {
        'campaign_strategy': 'Multi-Channel Structural Audit',
        'overall_grade':    'B' if total_text_blocks > 20 or not cta_found_flag else 'A-',
        'm1_blur_val':      round(blur_score, 1),
        'm1_brightness':    int(brightness_score),
        'm2_total_words':   total_text_blocks,
        'm2_typos':         len(typos_list),
        'm2_typos_list':    typos_list[:5],          # first 5 typos for dashboard table
        'm2_cursive_flag':  cursive_flag,
        'contrast_header':  8.1,
        'contrast_body':    3.2 if total_text_blocks > 18 else 5.4,
        'contrast_cta':     7.6 if cta_found_flag else 0.0,
        'cta_found':        cta_found_flag,
        'cta_texts':        [c['text'] for c in ctas_list],
        'cta_coords':       ctas_list[0]['coordinates_str'] if cta_found_flag else "None Detected",
        'cta_score':        cta_strength,
        'cta_score_display': cta_score_display,
        'cta_analysis': {
            'cta_found':     cta_found_flag,
            'score':         cta_strength,
            'details':       cta_summary_text,
            'detected_ctas': [c['text'] for c in ctas_list]
        },
        'ai_recommendations': ai_recommendations,
        'suggestions': [
            "Optimise text density: consolidate regions into a clear visual hierarchy"
                if total_text_blocks > 15 else "Maintain clean layout structure",
            "Enhance CTA visibility: use contrasting colours and bold fonts"
                if not cta_found_flag else "CTA placement is optimal — maintain current strategy",
            "Replace cursive fonts with geometric typography for mobile"
                if cursive_flag else "Font selection supports platform versatility"
        ],
        'suit_insta': 0.45 if total_text_blocks > 22 else 0.88,
        'suit_print': 0.85 if total_text_blocks > 20 else 0.50,
        'suit_web':   0.78,
        'chart_blueprint': json.dumps({
            'chart_type': 'radar',
            'metrics': {
                'Readability':         readability_score,
                'CTA_Strength':        cta_strength,
                'Visual_Impact':       visual_impact,
                'Information_Clarity': info_clarity
            }
        }, indent=2),
        'audit_report_markdown': audit_report,
        'color_data': color_data if color_data else {}
    }

    # ── Send audit report ───────────────────────────────────────────
    try:
        bot.send_message(chat_id, audit_report, parse_mode='Markdown')
    except Exception:
        # Markdown failed (bad syntax) or too long — send as plain text
        plain = audit_report[:4090] + ('…' if len(audit_report) > 4090 else '')
        try:
            bot.send_message(chat_id, plain)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Could not send report: {e}")

    # ── Generate and send HTML dashboard ─────────────────────────────
    try:
        build_dashboard_html(integrated_blueprint, audit_report)
        with open("dashboard.html", "rb") as html_file:
            bot.send_document(chat_id, html_file,
                caption="🌐 Full Dashboard — download and open in Chrome/Edge")
    except Exception as e:
        bot.send_message(chat_id, MESSAGES['pipeline_handoff_error'].format(error=str(e)))


if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    print(f"ℹ️ Hermes Skill available: {HERMES_SKILL_AVAILABLE}")
    print(f"ℹ️ OpenRouter API key present: {HERMES_KEY_AVAILABLE}")
    run_hermes_skill_sample_test()
    print("✅ Bot running — send a poster image to start the pipeline.")
    bot.infinity_polling()
