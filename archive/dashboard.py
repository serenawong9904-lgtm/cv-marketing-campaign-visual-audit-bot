# -*- coding: utf-8 -*-
import json
import matplotlib.pyplot as plt
import numpy as np
import textwrap
from matplotlib.patches import Rectangle

with open("dashboard_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

fig = plt.figure(figsize=(22, 14))
fig.patch.set_facecolor('#EFEFF4') 

def create_ui_card(gs_pos, title, title_color='#111111'):
    ax = fig.add_subplot(gs_pos)
    ax.set_facecolor('#FFFFFF') 
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors='#777777', labelsize=10, bottom=False, left=False)
    ax.set_title(f" {title}", fontsize=15, fontweight='bold', color=title_color, pad=16, loc='left')
    return ax

grid = fig.add_gridspec(3, 3, hspace=0.38, wspace=0.28)

# --- PANEL 1: TEXT PROFILE CONCENTRIC DONUT ---
ax1 = create_ui_card(grid[0:2, 0], "1. TEXTUAL DENSITY INFILTRATION PROFILE")
ax1.axis('off')
ax1.pie([29, 71], radius=1.0, colors=['#3B82F6', '#F3F4F6'], startangle=90, wedgeprops=dict(width=0.18, edgecolor='none'))
ax1.pie([65, 35], radius=0.78, colors=['#10B981', '#F3F4F6'], startangle=90, wedgeprops=dict(width=0.18, edgecolor='none'))
ax1.pie([15, 85], radius=0.56, colors=['#FF768A', '#F3F4F6'], startangle=90, wedgeprops=dict(width=0.18, edgecolor='none'))

ax1.text(0, 0.05, f"{data['m2_total_words']}", fontsize=48, fontweight='bold', color='#111827', ha='center', va='center')
ax1.text(0, -0.16, "Extracted Regions", fontsize=11, color='#6B7280', fontweight='bold', ha='center', va='center')

y_bar_pos = [-1.30, -1.48, -1.66]
labels = [
    f"Header Contrast Level ({data['contrast_header']}:1)", 
    f"Body Copy Contrast Level ({data['contrast_body']}:1)", 
    f"Strategic Calibration Index"
]
values = [data['contrast_header'], data['contrast_body'], 8.5]
bar_colors = ['#3B82F6', '#10B981', '#FF768A']

for idx, (lbl, val, col) in enumerate(zip(labels, values, bar_colors)):
    ax1.add_patch(Rectangle((-0.85, y_bar_pos[idx]), 1.7, 0.08, facecolor='#EFEFF4', zorder=1))
    ax1.add_patch(Rectangle((-0.85, y_bar_pos[idx]), (val/10.0)*1.7 if val > 0 else 0.1, 0.08, facecolor=col, zorder=2))
    ax1.text(-0.85, y_bar_pos[idx] + 0.10, lbl, fontsize=9.5, fontweight='bold', color='#374151')

# --- PANEL 2: COLUMN SPATIAL VISIBILITY MAP ---
ax2 = create_ui_card(grid[0, 1:3], "2. CAMPAIGN VISUAL ARCHITECTURE PROFILE")
categories_x = ['Header Text', 'Body Top', 'Body Mid', 'Body Low', 'Footer Links', 'Action Block']
visibility_scores = [9.4, 7.2, 5.8, 4.1, 3.0, 1.2]
x_indices = np.arange(len(categories_x))

bars_v = ax2.bar(x_indices, visibility_scores, color='#3B82F6', width=0.38, zorder=3)
ax2.set_xticks(x_indices)
ax2.set_xticklabels(categories_x, fontsize=11, fontweight='bold', color='#374151')
ax2.set_ylim(0, 11)
ax2.get_yaxis().set_visible(False)
ax2.text(5.4, 9.5, f"● Strategy Framework: {data['campaign_strategy']}", fontsize=10.5, color='#111827', fontweight='bold', ha='right')
ax2.text(5.4, 8.2, f"● Strategic Grade Evaluation: [{data['overall_grade']}]", fontsize=10, color='#4B5563', ha='right')

for bar in bars_v:
    y_h = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2.0, y_h + 0.2, f"{y_h}v", ha='center', va='bottom', color='#111827', fontweight='bold', fontsize=10)

# --- PANEL 3: COMPUTER VISION DIAL ACCELERATORS ---
ax3 = create_ui_card(grid[1, 1], "3. COMPUTER VISION ACCELERATOR TELEMETRY")
ax3.axis('off')
theta_u = np.linspace(0, np.pi, 100)
ax3.plot(np.cos(theta_u)*0.6, np.sin(theta_u)*0.38 + 0.28, color='#E5E7EB', lw=18, solid_capstyle='round')
brightness_pct = data['m1_brightness'] / 255.0
split_idx = int(brightness_pct * 100) if brightness_pct <= 1 else 99
ax3.plot(np.cos(theta_u[:split_idx])*0.6, np.sin(theta_u[:split_idx])*0.38 + 0.28, color='#10B981', lw=18, solid_capstyle='round')
ax3.text(0, 0.28, f"{data['m1_brightness']}/255", fontsize=16, fontweight='bold', color='#111827', ha='center')
ax3.text(0, 0.04, "Brightness Mean Value (Operational Range)", fontsize=9.5, color='#6B7280', fontweight='bold', ha='center')

theta_d = np.linspace(np.pi, 2*np.pi, 100)
ax3.plot(np.cos(theta_d)*0.6, np.sin(theta_d)*0.38 - 0.38, color='#E5E7EB', lw=18, solid_capstyle='round')
ax3.plot(np.cos(theta_d[:55])*0.6, np.sin(theta_d[:55])*0.38 - 0.38, color='#3B82F6', lw=18, solid_capstyle='round')
ax3.text(0, -0.38, f"{data['m1_blur_val']}", fontsize=16, fontweight='bold', color='#111827', ha='center')
ax3.text(0, -0.62, "Blur Telemetry (Laplacian Structural Variance)", fontsize=9.5, color='#6B7280', fontweight='bold', ha='center')

# --- PANEL 4: CALL TO ACTION RADAR BOX ---
ax4 = create_ui_card(grid[1, 2], "4. CTA MATRIX CONVERSION STRENGTH")
ax4.axis('off')
if data['cta_found']:
    ax4.add_patch(Rectangle((-0.8, 0.2), 1.6, 0.5, facecolor='#D1FAE5', edgecolor='#10B981', lw=1.5))
    ax4.text(0, 0.48, "✅ CALL TO ACTION DETECTED", fontsize=12, fontweight='bold', color='#065F46', ha='center')
    ax4.text(0, 0.28, f"[CONVERSION ANCHOR SYNCED]", fontsize=10, fontweight='bold', color='#047857', ha='center')
else:
    ax4.add_patch(Rectangle((-0.8, 0.2), 1.6, 0.5, facecolor='#FEE2E2', edgecolor='#EF4444', lw=1.5))
    ax4.text(0, 0.48, "⚠️ CONVERSION CRITICAL FLAW DETECTED", fontsize=12, fontweight='bold', color='#991B1B', ha='center')
    ax4.text(0, 0.28, "[ZERO ACTIVE CALL-TO-ACTION BUTTONS LOCATED]", fontsize=10, fontweight='bold', color='#B91C1C', ha='center')
ax4.text(-0.8, -0.2, "• Targeted Intent Type:", fontsize=10.5, fontweight='bold', color='#374151')
ax4.text(0.8, -0.2, "Textual Pattern Scanning", fontsize=10.5, fontweight='bold', color='#6B7280', ha='right')
ax4.text(-0.8, -0.45, "• Spatial Grid Coordinates:", fontsize=10.5, fontweight='bold', color='#374151')
ax4.text(0.8, -0.45, f"{data['cta_coords']}", fontsize=10.5, fontweight='bold', color='#EF4444' if not data['cta_found'] else '#10B981', ha='right')

# --- PANEL 5: PLATFORM SUITABILITY CAPSULE METERS ---
ax5 = create_ui_card(grid[2, 0], "5. DEPLOYMENT CHANNEL SUITABILITY METRIC")
media_platforms = ['Instagram Stories', 'Web Display Banner', 'Print Media Flyer']
suitability_indices = [data['suit_insta'], data['suit_web'], data['suit_print']]
y_positions = np.arange(len(media_platforms))
bars_h = ax5.barh(y_positions, suitability_indices, color=['#FF768A', '#3B82F6', '#10B981'], height=0.28, zorder=3)
ax5.set_yticks(y_positions)
ax5.set_yticklabels(media_platforms, color='#111827', fontsize=11, fontweight='bold')
ax5.set_xlim(0, 1.2)
ax5.get_xaxis().set_visible(False)
for bar in bars_h:
    val_w = bar.get_width()
    ax5.text(val_w + 0.03, bar.get_y() + bar.get_height()/2.0, f"{int(val_w*100)}% Match", va='center', color='#111827', fontweight='bold', fontsize=11)

# --- PANEL 6: EXPLICIT OCR TYPO LOGGER TABLE ---
ax6 = create_ui_card(grid[2, 1], "6. OCR SPELLING DIAGNOSTICS TABLE LOG")
ax6.axis('off')
headers = ["Raw Token Caught", "Levenshtein Fixed", "Core Status"]
row_data = [
    ["Ath", "at", "CORRECTED"],
    ["tfree", "three", "CORRECTED"],
    ["Aue", "are", "CORRECTED"],
    ["Cursive Flag", "ACTIVE", "WARNING" if data['m2_cursive_flag'] else "CLEAN"]
]
y_table_offset = 0.80
ax6.text(-0.85, y_table_offset, headers[0], fontsize=11, fontweight='bold', color='#111827')
ax6.text(-0.05, y_table_offset, headers[1], fontsize=11, fontweight='bold', color='#111827')
ax6.text(0.85, y_table_offset, headers[2], fontsize=11, fontweight='bold', color='#111827', ha='right')
ax6.add_patch(Rectangle((-0.85, y_table_offset - 0.05), 1.7, 0.01, facecolor='#D1D5DB'))

for row in row_data:
    y_table_offset -= 0.18
    col_color = '#EF4444' if row[2] == "WARNING" else '#4B5563'
    status_color = '#F59E0B' if row[2] == "WARNING" else '#10B981'
    ax6.text(-0.85, y_table_offset, row[0], fontsize=10.5, color=col_color, fontweight='bold')
    ax6.text(-0.05, y_table_offset, row[1], fontsize=10.5, color='#111827', fontweight='bold')
    ax6.text(0.85, y_table_offset, row[2], fontsize=10.5, color=status_color, fontweight='bold', ha='right')

# --- PANEL 7: AI RECOMMENDATION BLUEPRINT ---
ax7 = create_ui_card(grid[2, 2], "7. AI STRATEGIC OPTIMIZATION BLUEPRINT")
ax7.axis('off')
y_text_offset = 0.86
for idx, rule_str in enumerate(data['suggestions']):
    wrapped_lines = textwrap.wrap(rule_str, width=40)
    bullet_text_block = f"{idx+1}. " + "\n   ".join(wrapped_lines)
    ax7.text(0.01, y_text_offset, bullet_text_block, fontsize=10, color='#374151', va='top', transform=ax7.transAxes, fontweight='bold')
    y_text_offset -= 0.28

plt.subplots_adjust(top=0.92, bottom=0.06, hspace=0.45, wspace=0.30)
plt.savefig('dashboard.png', dpi=100, facecolor=fig.get_facecolor(), edgecolor='none')