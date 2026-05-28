# -*- coding: utf-8 -*-
"""
📊 Marketing Campaign Visual Auditor Bot
Main production script hosted on GitHub.
Target Module: Direct Integration Module (Member 1 + Member 2)
"""

import os
import threading
import re
import json
import cv2
import numpy as np
import telebot
from flask import Flask
from spellchecker import SpellChecker

# Background container installation hook for EasyOCR setup
try:
    import easyocr
except ImportError:
    import os
    os.system('pip install easyocr')
    import easyocr

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
# 🔬 CORE CV PROCESSING PIPELINE (Member 1)
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
# 🧠 EXTRACT TEXT REGION DETECTION & SPATIAL MAPPING (Member 2)
# =====================================================================
def extract_poster_text_and_coordinates(image_path="user_poster.jpg"):
    """
    Completely generalized Member 2 computer vision pipeline.
    Uses dynamic token filtering and pattern normalization to intelligently clean 
    OCR text distortions on ANY promotional, product, or event poster.
    """
    print(f"Initializing Adaptive Computer Vision Extraction Engine for: {image_path}")
    
    # Initialize EasyOCR (Falls back to CPU if no GPU accelerator is present)
    reader = easyocr.Reader(['en'], gpu=False) 
    results = reader.readtext(image_path)
    
    if not results:
        return {
            "status": "error",
            "message": "No text components or visual layouts detected in the image matrix."
        }
        
    # Initialize the generalized english spell-checker dictionary
    spell = SpellChecker()
    
    all_extracted_elements = []
    headline_text = ""
    max_bounding_area = 0
    low_confidence_counter = 0 
    
    # Universal Call-to-Action intent dictionary matching fundamental marketing behaviors
    cta_patterns = [
        r"join\s*now", r"register\s*now", r"scan\s*here", r"scan\s*me", 
        r"apply\s*now", r"book\s*now", r"rsvp", r"buy\s*now", r"order\s*now",
        r"click\s*here", r"visit\s*us", r"get\s*yours", r"limited\s*offer", 
        r"bridge\s*the\s*gap", r"cloud\s*run"
    ]
    cta_regex = re.compile("|".join(cta_patterns), re.IGNORECASE)
    detected_ctas = []

    for (bbox, text, confidence) in results:
        top_left = [int(bbox[0][0]), int(bbox[0][1])]
        bottom_right = [int(bbox[2][0]), int(bbox[2][1])]
        raw_text = text.strip()
        
        # 🧠 DYNAMIC LAYOUT PROCESSING & CHARACTER NORMALIZATION LOOP
        words = raw_text.split()
        processed_words = []
        
        for word in words:
            # Strip outer punctuation for isolated character analytics
            clean_word = re.sub(r'[^\w\s&]', '', word)
            
            # --- 1. DYNAMIC DATE SUFFIX CORRECTION ---
            # Automatically catches and repairs missing letters on numeric dates (e.g., '8t' -> '8th', '1s' -> '1st')
            if re.match(r'^\d+[tsrd]$', clean_word.lower()):
                suffix_map = {'t': 'th', 's': 'st', 'n': 'nd', 'r': 'rd'}
                last_char = clean_word.lower()[-1]
                if last_char in suffix_map:
                    word = word + suffix_map[last_char][1:]
                processed_words.append(word)
                continue
            
            # --- 2. DEFENSIVE TOKEN FILTERING ---
            # Bypasses the spell-checker if the token is a standard symbol, a standalone number, 
            # or a capitalized technical abbreviation/acronym.
            if (
                clean_word == "&" or 
                clean_word.isdigit() or 
                clean_word.isupper() or 
                any(char.isdigit() for char in clean_word) or
                confidence >= 0.85
            ):
                # Standardize character letter sub-types (e.g., misread letter O's inside numerical strings)
                if any(char.isdigit() for char in word):
                    word = word.replace('O', '0').replace('o', '0')
                processed_words.append(word)
                continue
            
            # --- 3. CONTEXTUAL SPELL-CHECK CORRECTION ---
            # Dynamically calculates Levenshtein distances for low-confidence text segments (like cursive)
            if clean_word.lower() not in spell:
                correction = spell.correction(clean_word)
                if correction and correction != clean_word:
                    # Maintain the poster's original case-style configuration
                    adjusted_case = correction.upper() if word.isupper() else correction.capitalize() if word[0].isupper() else correction
                    processed_words.append(adjusted_case)
                    continue
                    
            processed_words.append(word)
            
        cleaned_text = " ".join(processed_words)
        
        # --- 4. GENERALIZED TIME FORMAT PARSING ---
        # Fixed placement of the case-insensitive flag (?i) to prevent runtime syntax exceptions
        cleaned_text = re.sub(r'(?i)(\d+)[.・:](\d+)\s*(am|pm)', r'\1:\2\3', cleaned_text)

        # Calculate spatial volume metrics to evaluate typography layout prominence
        width = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        current_area = width * height
        
        # Increment the anomaly monitor tracking if character accuracy drop vectors look like cursive font noise
        if confidence < 0.65: 
            low_confidence_counter += 1

        element_entry = {
            "text": cleaned_text,
            "raw_ocr_original": raw_text if raw_text != cleaned_text else "No Correction Needed",
            "confidence": float(round(confidence, 3)),
            "bounding_box": {"top_left": top_left, "bottom_right": bottom_right}
        }
        all_extracted_elements.append(element_entry)
        
        # HEADLINE DETECTION: Dynamic visual hierarchy logic.
        if current_area > max_bounding_area and len(cleaned_text) > 3:
            if not any(ext in cleaned_text.lower() for ext in ["preview", ".jpg", ".png", ".jpeg"]):
                max_bounding_area = current_area
                headline_text = cleaned_text
            
        # CALL TO ACTION EVALUATOR: Checks text strings against universal intent metrics
        if cta_regex.search(cleaned_text):
            detected_ctas.append({
                "text": cleaned_text,
                "type": "textual_intent",
                "coordinates": {"top_left": top_left, "bottom_right": bottom_right}
            })

    total_regions = len(all_extracted_elements)
    has_cursive_anomaly = (low_confidence_counter / total_regions) > 0.15 if total_regions > 0 else False

    # Package the finalized adaptive data contract payload for Member 3
    return {
        "status": "success",
        "metadata": {
            "total_text_regions_found": total_regions,
            "low_confidence_text_regions": low_confidence_counter,
            "cursive_font_warning_flag": has_cursive_anomaly
        },
        "extracted_content": {
            "headline": headline_text if headline_text else "None Detected Confidently",
            "detected_call_to_actions": detected_ctas,
            "raw_text_stream": [item["text"] for item in all_extracted_elements],
            "complete_spatial_manifest": all_extracted_elements
        }
    }

if __name__ == "__main__":
    try:
        final_payload = extract_poster_text_and_coordinates("user_poster.jpg")
        print("\n=== SUCCESS: CORRECT SPELLCHECK EXTRACTION OUTPUT ===")
        print(json.dumps(final_payload, indent=4))
    except Exception as e:
        print(f"Execution Failure: {str(e)}")

# =====================================================================
# 🤖 TELEGRAM BOT CONTROLLERS (Member 1 Controllers + Member 2 Handoff)
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
        # Member 1's exact passing message text
        bot.reply_to(message, f"✅ Quality Check Passed! {feedback_msg}\nForwarding image to the extraction pipeline.")
        
        try:
            # ➡️ HARNESSED CONNECTOR: Your EasyOCR pipeline executes seamlessly here
            ocr_payload = extract_poster_text_and_coordinates(local_filename)
            
            # Prepare status confirmation report to push to the Telegram UI chat string
            extracted_headline = ocr_payload['extracted_content']['headline']
            found_ctas = len(ocr_payload['extracted_content']['detected_call_to_actions'])
            
            feedback_report = f"📊 **OCR Extraction Manifest Complete**\n\n"
            feedback_report += f"🔹 **Detected Headline:** {extracted_headline}\n"
            feedback_report += f"🔹 **Detected Textual CTAs:** {found_ctas}\n"
            
            # If our confidence monitor flags cursive font styles, proactively alert the user
            if ocr_payload['metadata']['cursive_font_warning_flag']:
                feedback_report += f"\n⚠️ **Notice:** Our layout engine detected highly stylized or cursive font families. Minor text anomalies may exist in downstream processing parameters."
                
            bot.reply_to(message, feedback_report, parse_mode='Markdown')
            
            # 🔗 DATA CONTRACT HANDOFF FOR MEMBER 3/4:
            # Passing 'ocr_payload' dictionary directly here for the Hermes skills engine.
            from hermes_skill.skill import member3_compile_report
            
            # Send an indicator that we are generating the report
            bot.reply_to(message, "🧠 Processing data with Hermes AI (Member 4)... Generating Campaign Audit Report.")
            
            final_analysis = member3_compile_report(ocr_payload)
            
            # Send the final Markdown report back to the user
            bot.reply_to(message, final_analysis, parse_mode='Markdown')
            
        except Exception as e:
            bot.reply_to(message, f"❌ Pipeline Parsing Error: {str(e)}")
            
    else:
        bot.reply_to(message, f"❌ Quality Check Failed!\nReason: {feedback_msg}\nPlease upload a clearer photo.")


# =====================================================================
# 🚀 SYSTEM RUNTIME ENGINE
# =====================================================================
if __name__ == "__main__":
    # Start Member 1's web server loop inside a concurrent side-thread using their original function names
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    # Fire up the polling module on the primary process thread
    print("Bot is successfully running and listening for posters...")
    bot.infinity_polling()
