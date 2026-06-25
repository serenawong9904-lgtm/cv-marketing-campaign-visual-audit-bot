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
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from spellchecker import SpellChecker
from pathlib import Path
import yaml
import spacy
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "marketing-visual-audit", "scripts"))

from vision_pipeline import check_image_quality, extract_poster_text_and_coordinates
from build_dashboard import (
    extract_chart_metrics_from_report,
    calculate_cta_score_rubric,
    extract_cta_section_from_report,
    extract_ai_recommendations_from_report
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from color_layout_analysis import compile_color_data

# ── AI Skill (AI report generator) ───────────────────────────────
MVA_SAMPLE_HEALTH = "Not tested"
MVA_KEY_AVAILABLE = False
try:
    from importlib import import_module
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "marketing-visual-audit", "scripts"))
    skill_module = import_module("skill")
    member3_compile_report = skill_module.member3_compile_report
    generate_bot_response = getattr(skill_module, "generate_bot_response", None)
    OPENROUTER_KEY_AVAILABLE = skill_module.OPENROUTER_KEY_AVAILABLE
    MVA_SKILL_AVAILABLE = True
    MVA_KEY_AVAILABLE = OPENROUTER_KEY_AVAILABLE
except Exception as e:
    MVA_SKILL_AVAILABLE = False
    print(f"⚠️ marketing-visual-audit skill unavailable ({e}); falling back to local report generation.")

try:
    import easyocr
except ImportError:
    os.system('pip install easyocr')
    import easyocr


# =====================================================================
# 📋 LOAD ASSETS FROM marketing-visual-audit FOLDER
# =====================================================================
def load_mva_skill_assets():
    mva_path = Path(__file__).parent / "marketing-visual-audit" / "assets"
    with open(mva_path / "messages.yaml", "r", encoding="utf-8") as f:
        messages = yaml.safe_load(f)
    with open(mva_path / "markdown_template.md", "r", encoding="utf-8") as f:
        markdown_template = f.read()
    with open(mva_path / "sample_input.yaml", "r", encoding="utf-8") as f:
        sample_input = yaml.safe_load(f)
    return messages, markdown_template, sample_input

MESSAGES, MARKDOWN_TEMPLATE, MVA_SAMPLE_INPUT = load_mva_skill_assets()

# =====================================================================
# 🧾 MEMBER 3 (LOCAL FALLBACK): Fill Markdown Template
# =====================================================================
def fill_markdown_template(ocr_data, metrics):
    readability_score = 85 if not ocr_data['metadata']['cursive_font_warning_flag'] else 65
    ctas_list         = ocr_data['extracted_content']['detected_call_to_actions']
    raw_text_stream   = ocr_data['extracted_content']['raw_text_stream']
    headline_text     = ocr_data['extracted_content']['headline']
    
    # Use rubric-based CTA scoring instead of binary
    cta_score_0_to_100 = calculate_cta_score_rubric(ctas_list, raw_text_stream, headline_text)
    cta_score          = cta_score_0_to_100  # Keep 0-100 for chart
    
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

    local_calc_score = readability_score
    if not ctas_list:
        local_calc_score -= 15

    if local_calc_score >= 80:
        local_grade = "A-"
    elif local_calc_score >= 70:
        local_grade = "B+"
    elif local_calc_score >= 60:
        local_grade = "B"
    elif local_calc_score >= 50:
        local_grade = "B-"
    else:
        local_grade = "C+"

    report = MARKDOWN_TEMPLATE.replace(
        "[Provide a 2-3 sentence summary evaluating the overall poster design based on text regions and CTAs.]",
        f"This marketing poster presents {total_regions} text regions {cta_presence_text} "
        f"The layout achieves a {'strong' if total_regions < 15 else 'moderate'} information hierarchy. "
        f"Overall strategic grade: {'A+' if cta_score >= 80 and total_regions < 15 else 'A' if cta_score >= 70 else 'B+'}"
    ).replace("[Number of text regions]", str(total_regions)
    ).replace("[Comment on cursive font warnings or readability]", cursive_comment
    ).replace("[Is it too cluttered or well-spaced?]", layout_comment
    ).replace("[List of CTAs]", cta_text
    ).replace("[X]/10", f"{int(cta_score / 10)}/10"
    ).replace("[Why the CTA is strong, weak, or missing]",
              f"CTA strength: {int(cta_score)}/100 — Strong action prompts with clear contact paths." if cta_score >= 70
              else f"CTA strength: {int(cta_score)}/100 — Moderate CTA; could improve visibility." if cta_score >= 50
              else f"CTA strength: {int(cta_score)}/100 — Weak or missing CTA; add urgency + contact info."
    ).replace("[Actionable suggestion 1]",
              "Optimise text density: consolidate regions into a clear visual hierarchy"
              if total_regions > 15 else "Maintain clean layout structure"
    ).replace("[Actionable suggestion 2]",
              "Enhance CTA visibility: add action verbs + urgency words + multiple contact paths"
              if cta_score < 70 else "CTA placement is optimal — maintain current strategy"
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
            "CTA_Strength":       cta_score,
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
    """Use AI Skill when available; fall back to local markdown template."""
    payload = {
        "metadata":         ocr_data["metadata"],
        "extracted_content": ocr_data["extracted_content"],
        "quality_metrics": {
            "blur_score":       metrics["blur_score"],
            "brightness_score": metrics["brightness_score"]
        }
    }
    if MVA_SKILL_AVAILABLE:
        if not MVA_KEY_AVAILABLE:
            print("⚠️ OpenRouter key missing — falling back to local report.")
            return fill_markdown_template(ocr_data, metrics)
        try:
            report = member3_compile_report(payload)
            if isinstance(report, str) and (report.startswith("❌") or len(report.strip()) < 150 or "User safety" in report):
                return fill_markdown_template(ocr_data, metrics)
            if not report or not report.strip():
                return fill_markdown_template(ocr_data, metrics)
            return report
        except Exception as e:
            print(f"⚠️ AI Skill failed: {e}")
            return fill_markdown_template(ocr_data, metrics)
    return fill_markdown_template(ocr_data, metrics)


def run_mva_skill_sample_test():
    global MVA_SAMPLE_HEALTH
    if not MVA_SKILL_AVAILABLE:
        MVA_SAMPLE_HEALTH = "AI Skill unavailable; fallback report generation active."
        print(f"ℹ️ {MVA_SAMPLE_HEALTH}")
        return
    try:
        sample_report = member3_compile_report(MVA_SAMPLE_INPUT)
        if sample_report and not sample_report.startswith("❌"):
            MVA_SAMPLE_HEALTH = "AI Skill sample payload executed successfully."
        else:
            MVA_SAMPLE_HEALTH = "AI Skill returned a fallback or error response."
    except Exception as e:
        MVA_SAMPLE_HEALTH = f"AI Skill sample test failed: {e}"
    print(f"ℹ️ {MVA_SAMPLE_HEALTH}")


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
      <div class="sval" style="font-size:1.5rem;">{cta_score_display}</div>
      <div class="ssub">Rubric Assessment</div>
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
            <div class="ir"><span class="il">CTA Status:</span><span class="iv">{cta_score_display}</span></div>
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
      <span class="cta-badge {cta_badge_cls}">Score: {cta_score_display}</span>
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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ BOT_TOKEN is missing! Please set it in your .env file.")

bot = telebot.TeleBot(BOT_TOKEN)

# Global dictionary to store processed data for each user
USER_SESSIONS = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, MESSAGES['welcome_message'], parse_mode='Markdown')


@bot.message_handler(commands=['end'])
def send_end_message(message):
    bot.reply_to(message, MESSAGES['end_message'], parse_mode='Markdown')


@bot.message_handler(func=lambda _: True, content_types=['text'])
def handle_text_fallback(message):
    if message.text.strip().lower() in ('/end', '/start', '/help'):
        return
        
    if MVA_SKILL_AVAILABLE and generate_bot_response:
        bot.send_chat_action(message.chat.id, 'typing')
        bot.reply_to(message, "🧠 Agent thinking...")
        reply = generate_bot_response(message.text)
        bot.send_message(message.chat.id, reply)
    else:
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
    
    def get_metric(metrics_dict, standard_key, fallback_val):
        if not metrics_dict:
            return fallback_val
        if standard_key in metrics_dict:
            return metrics_dict[standard_key]
        norm_std = standard_key.lower().replace('_', '')
        for k, v in metrics_dict.items():
            if k.lower().replace('_', '') == norm_std:
                return v
        return fallback_val

    readability_score = get_metric(report_metrics, 'Readability',    85 if not cursive_flag else 65)
    # For CTA, prefer LLM's assessment; but ensure it's a proper rubric score (0-100)
    cta_strength_from_llm = get_metric(report_metrics, 'CTA_Strength', None)
    if cta_strength_from_llm is not None:
        # If LLM returned 0-10, convert to 0-100
        if isinstance(cta_strength_from_llm, (int, float)) and cta_strength_from_llm <= 10:
            cta_strength = int(cta_strength_from_llm * 10)
        else:
            cta_strength = int(cta_strength_from_llm)
    else:
        # Fall back to local rubric-based scoring
        cta_strength = calculate_cta_score_rubric(ctas_list, ocr_result['extracted_content']['raw_text_stream'], ocr_result['extracted_content']['headline'])
    
    visual_impact     = get_metric(report_metrics, 'Visual_Impact',  80 if blur_score > 500 else 60)
    info_clarity      = get_metric(report_metrics, 'Information_Clarity', 75 if total_text_blocks < 15 else 55)

    cta_score_display = f"{int(cta_strength)}/100"

    cta_found_flag   = len(ctas_list) > 0
    cta_summary_text = extract_cta_section_from_report(audit_report) or (
        'CTAs found.' if cta_found_flag else 'No CTAs detected.'
    )
    ai_recommendations = extract_ai_recommendations_from_report(audit_report)

    # ── Build dashboard blueprint ───────────────────────────────────
    try:
        numeric_score = int(float(color_data.get('overall_campaign_score', 0)))
    except Exception:
        # Fallback to the local calculated score tracking variable if key doesn't exist
        try:
            numeric_score = int(readability_score)
            if not cta_found_flag:
                numeric_score -= 15
        except Exception:
            numeric_score = 50  # Absolute baseline fallback

    # 🛠️ Step B: Grade assignments mapped directly to performance score metrics
    if numeric_score >= 80:
        assigned_grade = "A-"
    elif numeric_score >= 70:
        assigned_grade = "B+"
    elif numeric_score >= 60:
        assigned_grade = "B"
    elif numeric_score >= 50:
        assigned_grade = "B-"
    else:
        assigned_grade = "C+"

    integrated_blueprint = {
        'campaign_strategy': 'Multi-Channel Structural Audit',
        'overall_grade':    assigned_grade,
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

    # ── Save session data and show menu ────────────────────────────
    USER_SESSIONS[chat_id] = {
        'blueprint': integrated_blueprint,
        'report': audit_report,
        'ocr_result': ocr_result,
        'blur_score': blur_score,
        'brightness_score': brightness_score
    }

    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("🌐 Generate HTML Dashboard", callback_data="btn_dashboard"),
        InlineKeyboardButton("📝 Full AI Audit Report", callback_data="btn_audit"),
        InlineKeyboardButton("🎯 Call-To-Action Score", callback_data="btn_cta"),
        InlineKeyboardButton("👁️ Image Quality Score", callback_data="btn_quality"),
        InlineKeyboardButton("🔍 OCR Extracted Text", callback_data="btn_ocr")
    )
    
    menu_text = "✅ **Poster successfully analyzed!** What would you like to view?"
    bot.reply_to(message, menu_text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_inline_button_clicks(call):
    chat_id = call.message.chat.id
    
    # Acknowledge the button click so the Telegram loading spinner stops
    bot.answer_callback_query(call.id)
    
    if chat_id not in USER_SESSIONS:
        bot.send_message(chat_id, "⚠️ Session expired. Please upload the poster again.")
        return
        
    session = USER_SESSIONS[chat_id]
    data = call.data
    
    if data == "btn_dashboard":
        bot.send_chat_action(chat_id, 'upload_document')
        try:
            build_dashboard_html(session['blueprint'], session['report'])
            with open("dashboard.html", "rb") as html_file:
                bot.send_document(chat_id, html_file, caption="🌐 Full Dashboard — download and open in Chrome/Edge")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Error building dashboard: {e}")
            
    elif data == "btn_audit":
        report = session['report']
        try:
            bot.send_message(chat_id, report, parse_mode='Markdown')
        except Exception:
            plain = report[:4090] + ('…' if len(report) > 4090 else '')
            bot.send_message(chat_id, plain)
            
    elif data == "btn_cta":
        blueprint = session['blueprint']
        cta_data = blueprint.get('cta_analysis', {})
        
        score_text = f"🎯 **Call-To-Action Analysis**\n\n"
        score_text += f"**Score:** {cta_data.get('score', 0)}/100\n"
        score_text += f"**Status:** {'Found' if cta_data.get('cta_found') else 'Not Found'}\n\n"
        
        if cta_data.get('cta_found'):
            score_text += "**Detected CTAs:**\n"
            for cta in cta_data.get('detected_ctas', []):
                score_text += f"- `{cta}`\n"
        
        score_text += f"\n**AI Analysis:**\n{cta_data.get('details', 'No detailed analysis available.')}"
        bot.send_message(chat_id, score_text, parse_mode='Markdown')
        
    elif data == "btn_quality":
        blur = session['blur_score']
        bright = session['brightness_score']
        
        quality_text = f"👁️ **Image Quality Assessment**\n\n"
        quality_text += f"**Blur Variance (Laplacian):** `{round(blur, 1)}`\n"
        quality_text += f"*(< 300 is considered too blurry)*\n\n"
        quality_text += f"**Mean Brightness:** `{round(bright, 1)}/255`\n"
        quality_text += f"*(< 40 is considered too dark)*"
        
        bot.send_message(chat_id, quality_text, parse_mode='Markdown')
        
    elif data == "btn_ocr":
        ocr = session['ocr_result']
        extracted = ocr.get('extracted_content', {})
        meta = ocr.get('metadata', {})
        
        ocr_text = f"🔍 **OCR Extraction Results**\n\n"
        ocr_text += f"**Detected Headline:**\n`{extracted.get('headline', 'None')}`\n\n"
        ocr_text += f"**Total Text Regions:** {meta.get('total_text_regions_found', 0)}\n"
        ocr_text += f"**Cursive Font Warning:** {'Yes ⚠️' if meta.get('cursive_font_warning_flag') else 'No ✅'}\n\n"
        
        raw = extracted.get('raw_text_stream', 'No text extracted')
        if len(raw) > 500:
            raw = raw[:500] + "...(truncated)"
            
        ocr_text += f"**Raw Text Stream:**\n{raw}"
        bot.send_message(chat_id, ocr_text, parse_mode='Markdown')

# =====================================================================
# 🎛️ COMMAND HANDLERS FOR INTERACTIVE MENU
# =====================================================================

def get_session(chat_id):
    if chat_id not in USER_SESSIONS:
        bot.send_message(chat_id, "⚠️ No active session found. Please upload a poster first!")
        return None
    return USER_SESSIONS[chat_id]




if __name__ == "__main__":
    bot.delete_webhook(drop_pending_updates=True)
    print(f"ℹ️ AI Skill available: {MVA_SKILL_AVAILABLE}")
    print(f"ℹ️ OpenRouter API key present: {MVA_KEY_AVAILABLE}")
    run_mva_skill_sample_test()
    print("✅ Bot running — send a poster image to start the pipeline.")
    bot.infinity_polling()
