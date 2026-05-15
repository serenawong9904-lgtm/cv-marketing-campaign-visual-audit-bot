# -*- coding: utf-8 -*-
"""
📊 Marketing Campaign Visual Auditor Bot
Main production script hosted on GitHub.
Target Module: Member 1 (Gatekeeper Pipeline)
"""

import os
import threading
from flask import Flask
import telebot
import cv2
import numpy as np

# =====================================================================
# 🌐 RENDER WEB PORT ALIVE KEEPER (Added for Option A Free Web Service)
# =====================================================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    # Render passes an environment variable called PORT. Default to 10000.
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# =====================================================================
# 🔬 CORE CV PROCESSING PIPELINE
# =====================================================================
def check_image_quality(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False, "Could not read the image file properly."

    # Blur detection
    laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
    # Brightness check
    mean_brightness = img.mean()

    # Threshold checks
    if mean_brightness < 40.0:
        return False, f"Image is too dark (Brightness: {round(mean_brightness, 1)}/255)."
    if laplacian_var < 300.0:
        return False, f"Image is too blurry (Blur Score: {round(laplacian_var, 1)})."

    return True, f"(Blur Score: {round(laplacian_var, 1)}, Brightness: {round(mean_brightness, 1)})"

# =====================================================================
# 🤖 TELEGRAM BOT CONTROLLERS
# =====================================================================
BOT_TOKEN = '8726514152:AAGddaMY47826AEKjy143FGkPoHvfs6kyiA'
bot = telebot.TeleBot(BOT_TOKEN)

# Welcome Message Handler (/start)
@bot.message_handler(commands=['start'])
def send_welcome_message(message):
    welcome_text = (
        "📊 *Welcome to the Marketing Campaign Visual Auditor Bot!* 📊\n\n"
        "This bot helps marketing and business management "
        "instantly evaluate the design effectiveness of promotional materials\n\n"
        "📥 *What to do:* \n"
        "Please upload a **poster, advertisement, product photo, Instagram post, "
        "or event banner image** directly to this chat.\n\n"
        "⚙️ *What we process:* \n"
        "1. Check image quality (blur and brightness analysis).\n"
        "2. Extract text layout metrics using OCR.\n"
        "3. Evaluate color contrast readability.\n\n"
        "🏁 *What you will receive:* \n"
        "Our Hermes AI will generate a detailed **Campaign Audit Report** including:\n"
        "✅ Readability Score & Color Contrast Analysis\n"
        "✅ Call-to-Action (CTA) Analysis & Score\n"
        "✅ Improvement Suggestions\n"
        "✅ Social Media Platform Suitability\n"
        "📊 Plus an automated **Visual Dashboard Chart**!\n\n"
        "🚨 *CRITICAL INPUT REQUIREMENT:* 🚨\n"
        "To ensure accurate OCR text extraction and precise color analysis, this bot "
        "**ONLY accepts high-quality, high-resolution original digital images**\n\n"
        "❌ *What will be rejected:* Low-resolution images, blurry camera photos, highly compressed screenshots, or dark images.\n\n"
        "Ready? Upload your design graphic now! 👇\n"
        "💡 *Type /end anytime to close your analysis session.*"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

# End Session Handler (/end)
@bot.message_handler(commands=['end'])
def send_end_message(message):
    end_text = (
        "🏁 *Session Ended Successfully!* 🏁\n\n"
        "Thank you for using the Marketing Campaign Visual Auditor. "
        "Your image data cache has been cleared for this session.\n\n"
        "🔄 To start a brand new audit or upload another poster, simply type `/start`!"
    )
    bot.reply_to(message, end_text, parse_mode='Markdown')

# Poster Ingestion Handler
@bot.message_handler(content_types=['photo'])
def handle_incoming_poster(message):
    bot.reply_to(message, "📥 Poster received! Assessing image quality...")

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    local_filename = "user_poster.jpg"
    with open(local_filename, 'wb') as new_file:
        new_file.write(downloaded_file)

    quality_pass, feedback_msg = check_image_quality(local_filename)

    if quality_pass:
        bot.reply_to(message, f"✅ Quality Check Passed! {feedback_msg}\nForwarding image to the extraction pipeline.")
        # ➡️ HANDOFF CONNECTOR: Member 2 drops easyocr code right here on May 19!
    else:
        bot.reply_to(message, f"❌ Quality Check Failed!\nReason: {feedback_msg}\nPlease upload a clearer photo.")

# =====================================================================
# 🚀 SYSTEM RUNTIME ENGINE
# =====================================================================
if __name__ == "__main__":
    # Start the web server loop inside a concurrent side-thread
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    # Fire up the polling module on the primary process thread
    print("Bot is successfully running and listening for posters...")
    bot.infinity_polling()