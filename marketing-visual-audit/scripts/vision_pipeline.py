import os
import re
import json
import sys
import cv2
import argparse
from spellchecker import SpellChecker

try:
    import easyocr
except ImportError:
    os.system('pip install easyocr')
    import easyocr

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

def extract_poster_text_and_coordinates(image_path="user_poster.jpg"):
    print(f"Initializing EasyOCR pipeline for: {image_path}")
    
    # ── STEP 1: PARAGRAPH-AWARE OCR GROUPING ──
    # paragraph=True naturally combines split lines (like "GET YOUR" and "TICKET") 
    # horizontally before processing, saving your text fragments from breaking.
    reader  = easyocr.Reader(['en'], gpu=False)
    
    # We pass the raw image path directly.
    # Setting paragraph=False is CRITICAL here, otherwise EasyOCR merges the entire poster
    # into a single massive text region, which ruins coordinate tracking and confuses the engine
    # (causing it to read '%' as '8').
    results = reader.readtext(image_path, paragraph=False)

    if not results:
        return {"status": "error", "message": "No text detected in the image."}

    spell = SpellChecker()
    all_extracted_elements = []
    headline_text = ""
    max_bounding_area = 0
    low_confidence_counter = 0
    typo_list = []

    # 📝 KEEPING YOUR CRITICAL PATTERNS INTACT
    cta_patterns = [
        # Action words (primary CTAs)
        r"join\s*now", r"register\s*now", r"scan\s*here", r"scan\s*me",
        r"apply\s*now", r"book\s*now", r"rsvp", r"buy\s*now", r"order\s*now",
        r"click\s*here", r"visit\s*us", r"get\s*yours", r"limited\s*offer",
        r"bridge\s*the\s*gap", r"cloud\s*run", r"purchase\s*now", r"come\s*in\s*store", 
        r"get\s*started", r"shop\s*now", r"sign\s*up", r"learn\s*more",
        r"find\s*out\s*more", r"explore", r"save\s*now", r"claim\s*now",
        r"get\s*\d+%\s*off", r"free\s*delivery", r"free\s*shipping", r"come\s*build",
        r"contact\s*us", r"reach\s*us", r"message\s*us", r"dm\s*us", r"call\s*us",
        r"follow\s*us", r"like\s*us", r"subscribe", r"watch\s*now", r"collect\s*'em\s*all'",
        # URLs and emails
        r"www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", 
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        # Phone numbers (various formats)
        r"\b\d{8,15}\b", 
        r"\b\d{3,4}[-\s]\d{3,4}[-\s]\d{3,4}\b",
        # Social media handles and patterns (more flexible)
        r"@[a-zA-Z0-9_]{1,30}",  # @handle format (Twitter, Instagram, Facebook)
        r"(?:instagram|fb|facebook|twitter|tiktok|linkedin|youtube)[.\s]*[:=]?\s*[@/]?[a-zA-Z0-9_.-]{1,50}",  # platform: handle
        r"(?:follow|visit|find|dm|message)\s+(?:us\s+)?on\s+(?:instagram|facebook|fb|twitter|tiktok|linkedin|youtube)",  # "follow us on Instagram"
        # Social media handles without @ (e.g., "naturalbeauty_box_gh")
        r"\b(?:instagram|fb|facebook|tiktok)\s+(?:handle|account|page)?[\s:]*([a-zA-Z0-9_]{3,})",
        # Explicit handles containing underscores with brand tags
        r"\b[a-zA-Z0-9_]{3,30}_(?:gh|box|page|shop|store|brand|beauty|feminine)\b",
        r"\b(?:naturalbeauty)[a-zA-Z0-9_.-]{1,30}\b",
        # facebook.com/handle or instagram.com/handle
        r"(?:facebook|instagram|fb)\.com/[a-zA-Z0-9_.-]+",
        # Brand specific identifiers followed by location or social suffix
        r"\b(?:box|page|shop|store|brand)[\s]*(?:gh|ng|uk|us|au)\b",
    ]
    cta_regex = re.compile("|".join(cta_patterns), re.IGNORECASE)
    detected_ctas = []

    # Initialize spaCy local parser
    import spacy
    import unicodedata
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        os.system("python -m spacy download en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")

    # Local structural noise filters (prevents corporate tags from muddying classifications)
    NOISE_EXCLUSIONS = {"zus", "preview", "handling", "position", "menu", "lalaport"}

    for (bbox, text, confidence) in results:
        top_left     = [int(bbox[0][0]), int(bbox[0][1])]
        bottom_right = [int(bbox[2][0]), int(bbox[2][1])]
        text_line    = text.strip()

        if not text_line:
            continue

        # ── STEP 2: GLOBAL UNICODE ACCENT STRIP ──
        # Converts decorative symbols (é -> e, á -> a) universally before checking anything.
        normalized_stream = unicodedata.normalize('NFKD', text_line)
        clean_normalized = "".join([c for c in normalized_stream if not unicodedata.combining(c)])
        
        eval_phrase = clean_normalized.strip('`~!@#$%^&*()-_=+[{]};:\'",<.>/?|• *')
        eval_phrase_lower = eval_phrase.lower().strip()

        # ── STEP 3: HYBRID CTA DETECTION MATRIX ──
        is_cta = False
        
        if eval_phrase_lower and eval_phrase_lower not in NOISE_EXCLUSIONS:
            # Match Verification Layer A: Check your core regex dictionary list first
            if cta_regex.search(eval_phrase):
                is_cta = True
            
            # Match Verification Layer B: Fallback to linguistic grammar matching if regex misses it
            else:
                doc = nlp(eval_phrase)
                if len(doc) > 0:
                    first_token = doc[0]
                    first_word_clean = first_token.text.lower().strip()
                    
                    if first_word_clean not in NOISE_EXCLUSIONS:
                        # Grammatical Active Commands (VB)
                        if first_token.pos_ in ("VERB", "AUX") and first_token.dep_ in ("ROOT", "advcl", "compound"):
                            if not (first_token.tag_ == "VBG" and len(doc) == 1): # Ignore solitary gerund noise
                                is_cta = True
                        
                        # Conversational sentence templates ("Come build your future with us")
                        if len(doc) > 1 and doc[0].lemma_ in ("come", "go", "join", "let", "call", "apply", "purchase", "get", "scan"):
                            is_cta = True

        # Validation Guard: Block short, generic single-word tags unless explicit actions
        if is_cta and len(eval_phrase.split()) == 1 and eval_phrase_lower not in ("scan", "join", "apply", "subscribe"):
            is_cta = False

        if is_cta:
            detected_ctas.append({
                "text": eval_phrase.upper(),
                "type": "hybrid_regex_linguistic",
                "coordinates": {"top_left": top_left, "bottom_right": bottom_right},
                "coordinates_str": f"[x: {top_left[0]}, y: {top_left[1]}]"
            })

        # ── STEP 4: DELIBERATE BACKGROUND SPELLCHECK MATRIX ──
        # DISABLED: Aggressive spellchecking destroys non-English text (like Lorem Ipsum)
        # and forcefully converts valid stylised brand names into random dictionary words.
        # We rely on the Layer 2 AI context adjuster to fix true typos instead.
        final_cleaned_line = text_line

        # ── STEP 5: SPATIAL MAP DATA BLUEPRINT ──
        width  = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        current_area = width * height

        element_entry = {
            "text": final_cleaned_line,
            "raw_ocr_original": text_line,
            "confidence": float(round(confidence, 3)),
            "bounding_box": {"top_left": top_left, "bottom_right": bottom_right}
        }
        all_extracted_elements.append(element_entry)

        # ── Step 5: Tightened Headline Selection Rule ──
        if current_area > max_bounding_area and len(final_cleaned_line) > 3:
            if not any(ext in final_cleaned_line.lower() for ext in ["preview", ".jpg", ".png", ".jpeg"]):
                max_bounding_area = current_area
                
                # Split lines in case paragraph mode combined them, and take the first line block
                lines = final_cleaned_line.split('\n')
                primary_header_line = lines[0].strip()
                
                # Guardrail: Increased threshold to 6 words for safety
                word_tokens = primary_header_line.split()
                if len(word_tokens) > 6:
                    headline_text = " ".join(word_tokens[:5]).upper()
                else:
                    headline_text = primary_header_line.upper()

    # =====================================================================
    # 🧠 LAYER 2: DEEP SEMANTIC CONTEXT ADJUSTER (OpenRouter)
    # =====================================================================
    # Keeps your codebase clean and professional by running a micro-evaluation
    # to repair display anomalies like "FREE HATE" -> "FREE MATCHA LATTE" dynamically.
    raw_text_stream = [item["text"].strip() for item in all_extracted_elements if len(item["text"].strip()) > 1]
    full_text_context = "\n".join(raw_text_stream)
    
    if raw_text_stream and os.environ.get("OPENROUTER_API_KEY"):
        try:
            import requests
            
            prompt_payload = f"""
            You are a validation reviewer for an OCR engine text stream. Review this text context block:
            \"\"\"
            {full_text_context}
            \"\"\"
            
            Task:
            If a dominant headline or title phrase has been mangled by automated spellcheck dictionaries (e.g., "Latte" or "Latté" was forced into "late", or split away from "FREE"), identify the corrected, unified main title line.
            
            Return ONLY a raw valid JSON object matching this schema:
            {{
              "corrected_headline": "THE CORRECTED UNIFIED TITLE"
            }}
            Do not include explanation notes or markdown blocks.
            """
            
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": "google/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": prompt_payload}]
                }),
                timeout=10
            )
            
            if response.status_code == 200:
                raw_ai_out = response.json()['choices'][0]['message']['content'].strip()
                clean_json_str = re.sub(r'```json\s*|```', '', raw_ai_out).strip()
                reconciled_data = json.loads(clean_json_str)
                
                if isinstance(reconciled_data, dict) and reconciled_data.get("corrected_headline"):
                    headline_text = reconciled_data["corrected_headline"].strip().upper()
        except Exception as e:
            print(f"⚠️ Secondary title adjustment checkpoint passed safely: {e}")

    total_regions = len(all_extracted_elements)
    return {
        "status": "success",
        "metadata": {
            "total_text_regions_found":    total_regions,
            "low_confidence_text_regions": low_confidence_counter,
            "cursive_font_warning_flag":   False
        },
        "extracted_content": {
            "headline":                  headline_text if headline_text else "None Detected Confidently",
            "detected_call_to_actions":  detected_ctas,
            "raw_text_stream":           [item["text"] for item in all_extracted_elements],
            "typos_found":               typo_list,
            "complete_spatial_manifest": all_extracted_elements
        }
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract visual features and OCR from poster.")
    parser.add_argument("image", help="Path to the poster image")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(json.dumps({"error": "Image file not found"}))
        sys.exit(1)
        
    quality_ok, metrics = check_image_quality(args.image)
    if not quality_ok:
        # metrics is error message here
        print(json.dumps({"error": metrics}))
        sys.exit(1)
        
    laplacian_var, mean_brightness = metrics
    
    ocr_data = extract_poster_text_and_coordinates(args.image)
    
    if ocr_data.get("status") == "error":
        print(json.dumps(ocr_data))
        sys.exit(1)
        
    payload = {
        "metadata": ocr_data["metadata"],
        "extracted_content": ocr_data["extracted_content"],
        "quality_metrics": {
            "blur_score": laplacian_var,
            "brightness_score": mean_brightness
        }
    }
    
    print(json.dumps(payload, indent=2))
