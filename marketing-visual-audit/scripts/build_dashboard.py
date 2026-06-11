import json
import re
import sys
import argparse
import os

try:
    # Assuming color_layout_analysis is accessible
    from color_layout_analysis import compile_color_data
    COLOR_ANALYSIS_AVAILABLE = True
except ImportError:
    COLOR_ANALYSIS_AVAILABLE = False

def extract_chart_metrics_from_report(audit_report):
    try:
        json_match = re.search(r'```json\s*(.*?)\s*```', audit_report, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
            if 'metrics' in parsed:
                return parsed['metrics']
        json_blocks = re.findall(r'\{[^{}]*\}', audit_report)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if 'metrics' in parsed:
                    return parsed['metrics']
            except Exception:
                pass
        for key in ['"chart_type"', '"charttype"']:
            idx = audit_report.find(key)
            if idx != -1:
                start = audit_report.rfind('{', 0, idx)
                if start != -1:
                    decoder = json.JSONDecoder()
                    parsed, _ = decoder.raw_decode(audit_report[start:])
                    if 'metrics' in parsed:
                        return parsed['metrics']
    except Exception as e:
        print(f"Could not extract chart metrics from report: {e}")
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

def calculate_cta_score_rubric(detected_ctas, raw_text_stream, headline):
    if not detected_ctas:
        return 0
    action_verbs = []
    contact_paths = []
    platform_refs = []
    action_verb_patterns = [
        r"buy\s*now", r"sign\s*up", r"join\s*now", r"register\s*now", 
        r"contact\s*us", r"call\s*us", r"reach\s*us", r"message\s*us", 
        r"follow\s*us", r"click\s*here", r"learn\s*more", r"shop\s*now",
        r"apply\s*now", r"book\s*now", r"subscribe", r"get\s*started"
    ]
    action_verb_re = re.compile("|".join(action_verb_patterns), re.IGNORECASE)
    contact_path_patterns = [
        r"\b\d{8,15}\b", r"\b\d{3,4}[-\s]\d{3,4}[-\s]\d{3,4}\b",
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        r"www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    ]
    contact_path_re = re.compile("|".join(contact_path_patterns), re.IGNORECASE)
    platform_ref_patterns = [
        r"@[a-zA-Z0-9_]{1,30}",
        r"(?:instagram|fb|facebook|twitter|tiktok|linkedin|youtube)[.\s]*[:=]?\s*[@/]?[a-zA-Z0-9_.-]{1,50}",
        r"(?:facebook|instagram|fb)\.com/[a-zA-Z0-9_.-]+",
        r"[a-z][a-z0-9_]{2,}(?:\sblog|\spagina|\spage|\sbox)?$"
    ]
    platform_ref_re = re.compile("|".join(platform_ref_patterns), re.IGNORECASE)
    
    for cta in detected_ctas:
        text = cta.get('text', '').lower() if isinstance(cta, dict) else str(cta).lower()
        if action_verb_re.search(text):
            action_verbs.append(cta)
        elif platform_ref_re.search(text):
            platform_refs.append(cta)
        elif contact_path_re.search(text):
            contact_paths.append(cta)
            
    type_score = 0
    if action_verbs: type_score = 85
    elif contact_paths and platform_refs: type_score = 70
    elif contact_paths: type_score = 60
    elif platform_refs: type_score = 50
    
    cta_count = len(detected_ctas)
    count_bonus = 15 if cta_count >= 3 else (8 if cta_count == 2 else 0)
    
    combined_text = " ".join(raw_text_stream).lower() if raw_text_stream else ""
    combined_text += " " + headline.lower() if headline else ""
    urgency_bonus = 10 if re.search(r"\b(now|limited|exclusive|today|today\s*only|act\s*now|hurry|urgent|free|offer|special|sale)\b", combined_text) else 0
    
    contact_types = len([x for x in [bool(action_verbs), bool(contact_paths), bool(platform_refs)] if x])
    diversity_bonus = 15 if contact_types >= 3 else (8 if contact_types == 2 else 0)
    
    final_score = min(100, type_score + count_bonus + urgency_bonus + diversity_bonus)
    if final_score == 0 and detected_ctas:
        final_score = 35
    return int(final_score)

def build_dashboard_html(blueprint_data, report_text_log, html_filename="dashboard.html"):
    def _sec(keywords):
        return extract_report_section(report_text_log, keywords)

    readability_sec = _sec(['Readability', 'Visual Quality'])
    cta_sec         = _sec(['CTA Analysis', 'Call-to-Action (CTA) Analysis', 'Call to Action Analysis'])
    platform_sec    = _sec(['Platform Suitability'])
    suggestions = extract_ai_recommendations_from_report(report_text_log)
    if not suggestions:
        suggestions = blueprint_data.get('ai_recommendations', blueprint_data.get('suggestions', []))

    chart_metrics = extract_chart_metrics_from_report(report_text_log) or {}
    if not chart_metrics:
        try:
            bp_str    = blueprint_data.get('chart_blueprint', '{}')
            bp_parsed = json.loads(bp_str) if isinstance(bp_str, str) else bp_str
            chart_metrics = bp_parsed.get('metrics', {})
        except Exception:
            chart_metrics = {}

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

    try:
        score_pct   = int(float(overall_score))
        score_color = '#059669' if score_pct >= 70 else '#D97706' if score_pct >= 50 else '#DC2626'
        ring_bg     = f'conic-gradient({score_color} {score_pct}%, #E5E7EB 0%)'
    except Exception:
        score_pct   = 0
        score_color = '#6366F1'
        ring_bg     = 'conic-gradient(#6366F1 0%, #E5E7EB 0%)'

    cta_icon       = '✅' if cta_found else '❌'
    cta_label      = 'Found' if cta_found else 'Missing'
    cta_badge_cls  = 'cta-found' if cta_found else 'cta-missing'
    cta_num_cls    = 'badge-green' if cta_found else 'badge-red'
    cursive_cls    = 'tag-amber' if cursive_flag else 'tag-green'
    cursive_txt    = 'Detected' if cursive_flag else 'Clean'

    def _render(text):
        if not text: return ''
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

    def _render_full(text):
        rows = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                rows.append('<div style="height:8px;"></div>')
                continue
            if s.startswith('```'): continue
            s2 = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', s)
            if s.startswith('### '): rows.append(f'<div class="rh3">{s[4:]}</div>')
            elif s.startswith('## '): rows.append(f'<div class="rh2">{s[3:]}</div>')
            elif s.startswith('# '): rows.append(f'<div class="rh1">{s[2:]}</div>')
            elif s.startswith('- ') or s.startswith('* '): rows.append(f'<div class="rli">{s2[2:]}</div>')
            else: rows.append(f'<div class="rp">{s2}</div>')
        return '\n'.join(rows)

    report_html      = _render_full(report_text_log)
    readability_html = _render(readability_sec)
    cta_html        = _render(cta_sec)
    platform_html   = _render(platform_sec)

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
            chart_bars += f"""<div class="mrow"><div class="mhdr"><span class="mname">{label}</span><span class="mscore">{pct}/100</span></div><div class="btrack" style="background:{track};"><div class="bfill" style="width:{pct}%;background:{grad};"></div></div></div>"""

    read_bars = ''
    for label, key, grad in [('Text Readability', 'text_readability', 'linear-gradient(90deg,#8B5CF6,#A78BFA)'), ('Contrast Quality', 'contrast_quality', 'linear-gradient(90deg,#3B82F6,#60A5FA)'), ('Image Quality', 'image_quality', 'linear-gradient(90deg,#10B981,#34D399)'), ('Layout Clarity', 'layout_clarity', 'linear-gradient(90deg,#F59E0B,#FCD34D)')]:
        score = int(round(float(readability_scores.get(key, 0) or 0)))
        pct   = max(0, min(score, 100))
        grade = '🟢' if pct >= 80 else '🟡' if pct >= 60 else '🔴'
        read_bars += f"""<div class="mrow"><div class="mhdr"><span class="mname">{label}</span><span style="display:flex;gap:6px;align-items:center;"><span class="mscore">{pct}/100</span><span style="font-size:.75rem;">{grade}</span></span></div><div class="btrack"><div class="bfill" style="width:{pct}%;background:{grad};"></div></div></div>"""

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
        plat_bars += f"""<div class="platrow"><span class="platname">{name}</span><div class="btrack" style="height:10px;"><div class="bfill" style="width:{score}%;background:{pal[i % len(pal)]};"></div></div><span class="platpct">{score}%</span></div>"""

    swatches = ''
    if dominant_colors:
        swatches = '<div class="swatches">'
        for c in dominant_colors[:5]:
            swatches += f'<div class="sw-item"><div class="sw-box" style="background:{c.get("hex","#000")};"></div><span class="sw-hex">{c.get("hex","N/A")}</span><span class="sw-pct">{c.get("percentage",0)}%</span></div>'
        swatches += '</div>'

    bg_hex  = background_color.get('hex', '#000000')
    bg_chip = f'<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"><span style="width:16px;height:16px;background:{bg_hex};border-radius:3px;border:1px solid #E2E8F0;display:inline-block;"></span><span style="font-size:.82rem;font-weight:700;font-family:monospace;color:#374151;">{bg_hex}</span></span>'

    t_pct   = float(text_density.get('text_area_percent', 0) or 0)
    v_pct   = float(text_density.get('visual_area_percent', 0) or 0)
    density = ''
    if t_pct or v_pct:
        density = f"""<div style="margin-top:14px;"><div class="dlabel"><span>Text Coverage</span><span>{t_pct}%</span></div><div class="btrack"><div class="bfill" style="width:{t_pct}%;background:linear-gradient(90deg,#F43F5E,#FB7185);"></div></div><div class="dlabel" style="margin-top:10px;"><span>Visual Space</span><span>{v_pct}%</span></div><div class="btrack"><div class="bfill" style="width:{v_pct}%;background:linear-gradient(90deg,#10B981,#34D399);"></div></div></div>"""

    recs_html = ''
    if suggestions:
        for i, rec in enumerate(suggestions[:5], 1):
            recs_html += f'<div class="rec"><div class="rec-n">{i}</div><div class="rec-t">{rec}</div></div>'

    css = """<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;background:#F1F5F9;color:#0F172A;line-height:1.6;min-height:100vh;}
.page{max-width:1380px;margin:0 auto;padding:24px;}
.hero{background:linear-gradient(135deg,#1E40AF 0%,#7C3AED 55%,#DB2777 100%);border-radius:24px;padding:40px 44px;color:#fff;margin-bottom:20px;}
.hero h1{font-size:1.85rem;font-weight:800;margin-bottom:6px;letter-spacing:-.02em;}
.hero p{opacity:.85;font-size:.95rem;}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px;}
.stat{background:#fff;border-radius:16px;padding:18px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 12px rgba(0,0,0,.04);border:1px solid #E2E8F0;text-align:center;}
.slbl{font-size:.7rem;color:#64748B;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px;}
.sval{font-size:1.5rem;font-weight:800;color:#0F172A;}
.ssub{font-size:.76rem;color:#94A3B8;margin-top:3px;}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}
.g60{display:grid;grid-template-columns:1.6fr 1fr;gap:20px;margin-bottom:20px;}
.g1{margin-bottom:20px;}
.card{background:#fff;border-radius:20px;padding:26px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.04);border:1px solid #E2E8F0;}
.sbadge{display:flex;align-items:center;gap:10px;margin-bottom:18px;}
.bnum{width:30px;height:30px;border-radius:50%;font-weight:800;font-size:.82rem;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.badge-blue{background:#DBEAFE;color:#1D4ED8;}
.badge-purple{background:#EDE9FE;color:#5B21B6;}
.badge-green{background:#DCFCE7;color:#166534;}
.badge-red{background:#FEE2E2;color:#991B1B;}
.badge-amber{background:#FEF3C7;color:#92400E;}
.badge-indigo{background:#E0E7FF;color:#3730A3;}
.stitle{font-size:1rem;font-weight:700;color:#0F172A;}
.sring-wrap{display:flex;flex-direction:column;align-items:center;padding:22px;background:#F8FAFC;border-radius:16px;border:1px solid #E2E8F0;margin-bottom:14px;}
.sring{width:100px;height:100px;border-radius:50%;display:flex;align-items:center;justify-content:center;position:relative;}
.sring-in{position:absolute;width:72px;height:72px;background:#fff;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;}
.snum{font-size:1.4rem;font-weight:800;line-height:1;}
.sden{font-size:.63rem;color:#94A3B8;}
.cta-badge{display:inline-flex;align-items:center;gap:10px;padding:12px 20px;border-radius:999px;font-weight:700;font-size:1rem;margin-bottom:16px;}
.cta-found{background:#ECFDF5;color:#065F46;border:1.5px solid #6EE7B7;}
.cta-missing{background:#FEF2F2;color:#991B1B;border:1.5px solid #FCA5A5;}
.ir{display:flex;align-items:flex-start;gap:8px;margin-bottom:9px;font-size:.88rem;}
.il{color:#94A3B8;font-weight:600;min-width:115px;flex-shrink:0;}
.iv{color:#0F172A;font-weight:600;}
.tag{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:700;}
.tag-green{background:#DCFCE7;color:#166534;}
.tag-amber{background:#FEF3C7;color:#92400E;}
.mrow{margin-bottom:14px;}.mrow:last-child{margin-bottom:0;}
.mhdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;}
.mname{font-size:.88rem;font-weight:600;color:#374151;}
.mscore{font-size:.84rem;font-weight:700;color:#0F172A;}
.btrack{height:9px;background:#F1F5F9;border-radius:999px;overflow:hidden;}
.bfill{height:100%;border-radius:999px;}
.platrow{display:grid;grid-template-columns:155px 1fr 50px;align-items:center;gap:12px;margin-bottom:12px;}
.platrow:last-child{margin-bottom:0;}
.platname{font-size:.88rem;font-weight:600;color:#374151;}
.platpct{font-size:.88rem;font-weight:700;color:#0F172A;text-align:right;}
.rec{display:flex;align-items:flex-start;gap:14px;padding:14px 16px;background:#F8FAFC;border-radius:14px;border:1px solid #E2E8F0;margin-bottom:10px;}
.rec:last-child{margin-bottom:0;}
.rec-n{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#6366F1,#8B5CF6);color:#fff;font-weight:800;font-size:.82rem;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}
.rec-t{font-size:.88rem;color:#374151;font-weight:500;line-height:1.6;}
.swatches{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.sw-item{text-align:center;}
.sw-box{width:54px;height:54px;border-radius:12px;border:2px solid rgba(0,0,0,.06);box-shadow:0 2px 8px rgba(0,0,0,.08);}
.sw-hex{display:block;font-size:.7rem;font-weight:700;color:#374151;margin-top:5px;font-family:monospace;}
.sw-pct{display:block;font-size:.66rem;color:#94A3B8;}
.dlabel{display:flex;justify-content:space-between;font-size:.84rem;font-weight:600;color:#374151;margin-bottom:5px;}
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
  <div class="hero">
    <h1>📊 Marketing Campaign Visual Audit Dashboard</h1>
    <p>Automated visual audit · Upload your poster to receive a full campaign analysis</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="slbl">Overall Score</div><div class="sval" style="color:{score_color};">{overall_score}</div><div class="ssub">Grade: {overall_grade}</div></div>
    <div class="stat"><div class="slbl">CTA Status</div><div class="sval" style="font-size:1.5rem;">{cta_score_display}</div><div class="ssub">Rubric Assessment</div></div>
    <div class="stat"><div class="slbl">Text Regions</div><div class="sval">{total_regions}</div><div class="ssub">extracted by OCR</div></div>
    <div class="stat"><div class="slbl">Blur Score</div><div class="sval">{blur_val}</div><div class="ssub">Laplacian var.</div></div>
    <div class="stat"><div class="slbl">Brightness</div><div class="sval">{brightness_val}</div><div class="ssub">mean pixel / 255</div></div>
  </div>
  <div class="g1">
    <div class="card">
      <div class="sbadge"><div class="bnum badge-blue">1</div><span class="stitle">Audit Report</span></div>
      <div style="display:grid;grid-template-columns:1fr 320px;gap:20px;align-items:start;">
        <div class="rbox">{report_html}</div>
        <div>
          <div class="sring-wrap"><div class="sring" style="background:{ring_bg};"><div class="sring-in"><span class="snum" style="color:{score_color};">{overall_score}</span><span class="sden">/ 100</span></div></div><div style="text-align:center;margin-top:12px;"><div style="font-size:.74rem;color:#64748B;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">Campaign Score</div><div style="font-size:1.1rem;font-weight:800;color:#0F172A;margin-top:3px;">Grade: {overall_grade}</div></div></div>
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
  <div class="g2">
    <div class="card"><div class="sbadge"><div class="bnum badge-amber">4</div><span class="stitle">AI Improvement Suggestions</span></div>{recs_html}</div>
    <div class="card"><div class="sbadge"><div class="bnum badge-blue">📈</div><span class="stitle">Performance Metrics Blueprint</span></div><div class="sublbl">Scores from AI Audit Report</div>{chart_bars}</div>
  </div>
  <div class="g1"><div class="card"><div class="sbadge"><div class="bnum badge-indigo">5</div><span class="stitle">Platform Suitability</span></div>{plat_bars}</div></div>
  <div class="g1"><div class="card"><div class="sublbl">🎨 Dominant Color Palette</div>{swatches}<div class="ir" style="margin-top:10px;"><span class="il">Background:</span><span>{bg_chip}</span></div>{density}</div></div>
</div>
</body>
</html>"""

    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Dashboard generated at {os.path.abspath(html_filename)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate HTML dashboard from vision payload and markdown report.")
    parser.add_argument("vision_payload", help="Path to the vision JSON payload file")
    parser.add_argument("report", help="Path to the markdown report file")
    parser.add_argument("--image", help="Optional original image path for color analysis")
    args = parser.parse_args()

    with open(args.vision_payload, "r", encoding="utf-8") as f:
        ocr_result = json.load(f)

    with open(args.report, "r", encoding="utf-8") as f:
        audit_report = f.read()

    headline          = ocr_result.get('extracted_content', {}).get('headline', '')
    total_text_blocks = ocr_result.get('metadata', {}).get('total_text_regions_found', 0)
    cursive_flag      = ocr_result.get('metadata', {}).get('cursive_font_warning_flag', False)
    ctas_list         = ocr_result.get('extracted_content', {}).get('detected_call_to_actions', [])
    typos_list        = ocr_result.get('extracted_content', {}).get('typos_found', [])
    raw_text_stream   = ocr_result.get('extracted_content', {}).get('raw_text_stream', [])
    
    blur_score        = ocr_result.get('quality_metrics', {}).get('blur_score', 0)
    brightness_score  = ocr_result.get('quality_metrics', {}).get('brightness_score', 0)

    color_data = None
    if COLOR_ANALYSIS_AVAILABLE and args.image and os.path.exists(args.image):
        try:
            _, color_data = compile_color_data(args.image, ocr_result, blur_score=blur_score, brightness=brightness_score)
        except Exception as e:
            print(f"Color analysis failed: {e}")

    report_metrics = extract_chart_metrics_from_report(audit_report)
    
    def get_metric(metrics_dict, standard_key, fallback_val):
        if not metrics_dict: return fallback_val
        if standard_key in metrics_dict: return metrics_dict[standard_key]
        norm_std = standard_key.lower().replace('_', '')
        for k, v in metrics_dict.items():
            if k.lower().replace('_', '') == norm_std: return v
        return fallback_val

    readability_score = get_metric(report_metrics, 'Readability', 85 if not cursive_flag else 65)
    cta_strength_from_llm = get_metric(report_metrics, 'CTA_Strength', None)
    if cta_strength_from_llm is not None:
        cta_strength = int(cta_strength_from_llm * 10) if (isinstance(cta_strength_from_llm, (int, float)) and cta_strength_from_llm <= 10) else int(cta_strength_from_llm)
    else:
        cta_strength = calculate_cta_score_rubric(ctas_list, raw_text_stream, headline)
    
    visual_impact = get_metric(report_metrics, 'Visual_Impact', 80 if blur_score > 500 else 60)
    info_clarity  = get_metric(report_metrics, 'Information_Clarity', 75 if total_text_blocks < 15 else 55)

    cta_score_display = f"{int(cta_strength)}/100"
    cta_found_flag   = len(ctas_list) > 0
    cta_summary_text = extract_cta_section_from_report(audit_report) or ('CTAs found.' if cta_found_flag else 'No CTAs detected.')
    ai_recommendations = extract_ai_recommendations_from_report(audit_report)

    integrated_blueprint = {
        'campaign_strategy': 'Multi-Channel Structural Audit',
        'overall_grade':    'B' if total_text_blocks > 20 or not cta_found_flag else 'A-',
        'm1_blur_val':      round(blur_score, 1),
        'm1_brightness':    int(brightness_score),
        'm2_total_words':   total_text_blocks,
        'm2_typos':         len(typos_list),
        'm2_typos_list':    typos_list[:5],
        'm2_cursive_flag':  cursive_flag,
        'contrast_header':  8.1,
        'contrast_body':    3.2 if total_text_blocks > 18 else 5.4,
        'contrast_cta':     7.6 if cta_found_flag else 0.0,
        'cta_found':        cta_found_flag,
        'cta_texts':        [c['text'] for c in ctas_list],
        'cta_coords':       ctas_list[0]['coordinates_str'] if (cta_found_flag and len(ctas_list) > 0 and 'coordinates_str' in ctas_list[0]) else "None Detected",
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
            "Optimise text density: consolidate regions into a clear visual hierarchy" if total_text_blocks > 15 else "Maintain clean layout structure",
            "Enhance CTA visibility: use contrasting colours and bold fonts" if not cta_found_flag else "CTA placement is optimal — maintain current strategy",
            "Replace cursive fonts with geometric typography for mobile" if cursive_flag else "Font selection supports platform versatility"
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

    build_dashboard_html(integrated_blueprint, audit_report)
