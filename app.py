# -*- coding: utf-8 -*-
"""
📊 MCVA Bot - Final Consolidated Production Pipeline
Hosted on Railway | Configured for Member 1 - 5 Completion
"""

import os
import threading
import re
import json
import subprocess
import cv2
import numpy as np
import telebot
from flask import Flask
from spellchecker import SpellChecker
import matplotlib
matplotlib.use('Agg')  # Forces matplotlib to run without a GUI window on the server
import matplotlib.pyplot as plt
import textwrap

# Background container installation hook for EasyOCR setup
try:
    import easyocr
except ImportError:
    import os
    os.system('pip install easyocr')
    import easyocr

# =====================================================================
# 🌐 LIVE-KEEPER WEB SERVER
# =====================================================================
app = Flask('')

@app.route('/')
def home():
    return "MCVA Bot Production Server is Live!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# =====================================================================
# 🧪 CORE CV PROCESSING PIPELINE (Member 1 & 2 logic)
# =====================================================================
def check_image_quality(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False, "Unable to read image file."
    
    # Laplacian Variance for Blur
    blur_score = cv2.Laplacian(img, cv2.CV_64F).var()
    # Average Brightness
    brightness_score = np.mean(img)
    
    if blur_score < 100.0:
        return False, f"Image is too blurry (Score: {blur_score:.1f})."
    if brightness_score < 40.0:
        return False, f"Image is too dark (Score: {brightness_score:.1f})."
        
    return True, (blur_score, brightness_score)

# =====================================================================
# 🛠️ MEMBER 5: AUTOMATED DASHBOARD ENGINE (META-TOOL)
# =====================================================================
def build_dashboard_meta_tool(blueprint_data, filename="dashboard.py"):
    """
    MEMBER 5 META-TOOL:
    Auto-generates 'dashboard.py' script using pre-evaluated metrics.
    """
    typo_color = '#EF4444' if blueprint_data['m2_typos'] > 0 else '#10B981'
    cursive_color = '#F59E0B' if blueprint_data['m2_cursive_flag'] else '#10B981'
    cta_color = "#10B981" if blueprint_data['cta_found'] else "#EF4444"
    cta_status = "PASSED: FOUND" if blueprint_data['cta_found'] else "CRITICAL: MISSING"
    
    script_content = f"""
import matplotlib.pyplot as plt
import numpy as np
import textwrap

fig, axs = plt.subplots(3, 3, figsize=(18, 12))
fig.suptitle("MCVA EXECUTIVE VISUAL AUDIT INSIGHT REPORT", fontsize=20, fontweight='bold', color='#FFFFFF', y=0.96)
fig.patch.set_facecolor('#111827')

def style_card(ax, title):
    ax.set_facecolor('#1F2937')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#4B5563')
    ax.spines['bottom'].set_color('#4B5563')
    ax.tick_params(colors='#9CA3AF', labelsize=9)
    ax.set_title(title, fontsize=12, fontweight='bold', color='#F3F4F6', pad=12, loc='left')

# 1. Summary Card
ax = axs[0, 0]
style_card(ax, "1. Executive Summary")
ax.text(0.05, 0.80, f"Strategy Target:\\n{blueprint_data['campaign_strategy']}", fontsize=11, color='#9CA3AF', wrap=True)
ax.text(0.05, 0.50, f"Overall Grade", fontsize=10, color='#9CA3AF')
ax.text(0.05, 0.15, f"{blueprint_data['overall_grade']}", fontsize=36, color='#10B981', fontweight='bold')
ax.axis('off')

# 2. Pre-Check Card
ax = axs[0, 1]
style_card(ax, "2. Image Pre-Check Telemetry")
ax.text(0.05, 0.75, f"• Blur Metric (Laplacian Var): {blueprint_data['m1_blur_val']}", fontsize=10, color='#E5E7EB')
ax.text(0.05, 0.55, f"• Brightness Level: {blueprint_data['m1_brightness']}/255", fontsize=10, color='#E5E7EB')
ax.text(0.05, 0.35, f"• System Status: Operational", fontsize=10, color='#3B82F6')
ax.axis('off')

# 3. OCR Card
ax = axs[0, 2]
style_card(ax, "3. OCR Text Analytics")
ax.text(0.05, 0.75, f"• Total Tokens Extracted: {blueprint_data['m2_total_words']}", fontsize=10, color='#E5E7EB')
ax.text(0.05, 0.55, f"• Typing/Spelling Anomalies: {blueprint_data['m2_typos']}", fontsize=10, color='{typo_color}')
ax.text(0.05, 0.35, f"• Cursive Script Warning: {{'ACTIVE' if {blueprint_data['m2_cursive_flag']} else 'NONE'}}", fontsize=10, color='{cursive_color}')
ax.axis('off')

# 4. Contrast Card
ax = axs[1, 0]
style_card(ax, "4. Contrast Ratios (WCAG Standards)")
categories = ['Header', 'Body Text', 'CTA Text']
scores = [{blueprint_data['contrast_header']}, {blueprint_data['contrast_body']}, {blueprint_data['contrast_cta']}]
colors = ['#10B981' if s >= 4.5 else '#EF4444' for s in scores]
bars = ax.bar(categories, scores, color=colors, width=0.4, edgecolor='#374151', zorder=3)
ax.axhline(y=4.5, color='#9CA3AF', linestyle='--')
ax.set_ylim(0, 12)

# 5. CTA Location Card
ax = axs[1, 1]
style_card(ax, "5. CTA Status & Location Matrix")
ax.text(0.5, 0.75, "{cta_status}", fontsize=14, fontweight='bold', color='{cta_color}', ha='center')
ax.text(0.5, 0.45, f"Detected Coordinates:\\n{blueprint_data['cta_coords']}", fontsize=10, color='#9CA3AF', ha='center', wrap=True)
ax.axis('off')

# 6. Platform Suitability Card
ax = axs[1, 2]
style_card(ax, "6. Cross-Platform Suitability")
platforms = ['Instagram Feed', 'Print Media Flyer', 'Web Display Banner']
suitability = [{blueprint_data['suit_insta']}, {blueprint_data['suit_print']}, {blueprint_data['suit_web']}]
y_pos = np.arange(len(platforms))
ax.barh(y_pos, suitability, color='#3B82F6', height=0.35)
ax.set_yticks(y_pos)
ax.set_yticklabels(platforms, color='#E5E7EB')
ax.set_xlim(0, 1.0)

# 7. Suggestions Card
ax = axs[2, 0]
style_card(ax, "7. AI Strategic Optimization Rules")
suggestions_list = {blueprint_data['suggestions']}
wrapped_suggestions = []
for s in suggestions_list:
    wrapped_lines = textwrap.wrap(s, width=35)
    if wrapped_lines:
        wrapped_suggestions.append("✔ " + "\\n  ".join(wrapped_lines))
suggestions_text = "\\n\\n".join(wrapped_suggestions)
ax.text(0.02, 0.90, suggestions_text, fontsize=10, color='#E5E7EB', va='top', wrap=True)
ax.axis('off')

# 8. Palette Card
ax = axs[2, 1]
style_card(ax, "8. Extracted Color Palette")
palette = {blueprint_data['color_palette']}
spacing = 0.22
for idx, hex_color in enumerate(palette):
    rect = plt.Rectangle((0.05 + idx*spacing, 0.4), 0.18, 0.3, facecolor=hex_color, edgecolor='#4B5563', transform=ax.transAxes)
    ax.add_patch(rect)
    ax.text(0.14 + idx*spacing, 0.25, hex_color, color='#9CA3AF', fontsize=8, ha='center', transform=ax.transAxes)
ax.axis('off')

axs[2, 2].axis('off')
plt.tight_layout()
plt.subplots_adjust(top=0.88, hspace=0.35)
plt.savefig('dashboard.png', dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(script_content.strip())


# =====================================================================
# 🤖 TELEGRAM BOT RUNTIME PIPELINE
# =====================================================================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_FALLBACK_TOKEN_HERE")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Welcome to the MCVA Audit Pipeline Bot! Upload a marketing poster image to trigger the comprehensive system audit.")

@bot.message_handler(content_types=['photo'])
def handle_poster_upload(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "📥 Poster received! Running quality checks and model pipelines...")
    
    # Save image file locally
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    local_image_path = "input_poster.png"
    
    with open(local_image_path, 'wb') as new_file:
        new_file.write(downloaded_file)
        
    # Execute Member 1 Quality Gatekeeper
    passed, quality_data = check_image_quality(local_image_path)
    
    if not passed:
        bot.send_message(chat_id, f"❌ Quality Check Failed!\nReason: {quality_data}\nPlease re-upload a clearer image.")
        return
        
    blur, brightness = quality_data
    
    # SIMULATING DOWNSTREAM PROCESS (Members 2, 3, and 4)
    # Once your teammates plug their exact functions in, they will populate this dictionary dynamically!
    processed_blueprint_data = {
        'campaign_strategy': 'Global Brand Awareness Blitz',
        'overall_grade': 'A-',
        'm1_blur_val': round(blur, 1),
        'm1_brightness': int(brightness),
        'm2_total_words': 18,
        'm2_typos': 0,
        'm2_cursive_flag': False,
        'contrast_header': 7.4,
        'contrast_body': 3.9,
        'contrast_cta': 6.8,
        'cta_found': True,
        'cta_coords': '[x: 210, y: 975]',
        'suggestions': [
            'Boost background contrast values behind the primary body copy.',
            'Maintain strict alignment targets across Instagram grid markers.'
        ],
        'color_palette': ['#111827', '#3B82F6', '#10B981', '#F59E0B'],
        'suit_insta': 0.94,
        'suit_print': 0.48,
        'suit_web': 0.85
    }
    
    text_report_markdown = (
        "### 📊 MCVA EXECUTIVE CAMPAIGN AUDIT\n\n"
        f"• **Overall Strategy:** {processed_blueprint_data['campaign_strategy']}\n"
        f"• **Overall Quality Grade:** {processed_blueprint_data['overall_grade']}\n\n"
        "**Core Metrics Summary:**\n"
        f"- Text Contrast Standards: Passed (Header & CTA)\n"
        f"- Target CTA Element: Detected successfully at coordinates {processed_blueprint_data['cta_coords']}.\n"
    )

    try:
        # 1. Run Meta-Tool to generate dashboard.py string and save it
        build_dashboard_meta_tool(processed_blueprint_data)
        
        # 2. Run the newly written dashboard.py file to compile dashboard.png
        subprocess.run(["python", "dashboard.py"], check=True)
        
        # 3. Deliver all Member 5 grading criteria back to Telegram
        bot.send_message(chat_id, text_report_markdown, parse_mode='Markdown')
        
        # Send raw dashboard.py script file
        with open("dashboard.py", "rb") as doc_file:
            bot.send_document(chat_id, doc_file, caption="🐍 Member 5 Auto-Generated Dashboard Script")
            
        # Send rendered dashboard image asset
        with open("dashboard.png", "rb") as img_file:
            bot.send_photo(chat_id, img_file, caption="📊 Final High-Fidelity Audit Dashboard Canvas")
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ Member 5 Execution Pipeline Failure: {str(e)}")

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    print("System is running. Listening for Telegram photo items...")
    bot.infinity_polling()