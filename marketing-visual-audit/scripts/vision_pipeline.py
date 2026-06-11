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
    reader  = easyocr.Reader(['en'], gpu=False, verbose=False)
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
        r"bridge\s*the\s*gap", r"cloud\s*run",
        r"get\s*started", r"shop\s*now", r"sign\s*up", r"learn\s*more",
        r"find\s*out\s*more", r"explore", r"save\s*now", r"claim\s*now",
        r"get\s*\d+%\s*off", r"free\s*delivery", r"free\s*shipping",
        r"contact\s*us", r"reach\s*us", r"message\s*us", r"dm\s*us", r"call\s*us",
        r"follow\s*us", r"like\s*us", r"subscribe", r"watch\s*now",
        r"www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", 
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
        r"\b\d{8,15}\b", 
        r"\b\d{3,4}[-\s]\d{3,4}[-\s]\d{3,4}\b",
        r"@[a-zA-Z0-9_]{1,30}",
        r"(?:instagram|fb|facebook|twitter|tiktok|linkedin|youtube)[.\s]*[:=]?\s*[@/]?[a-zA-Z0-9_.-]{1,50}",
        r"(?:follow|visit|find|dm|message)\s+(?:us\s+)?on\s+(?:instagram|facebook|fb|twitter|tiktok|linkedin|youtube)",
        r"\b(?:instagram|fb|facebook|tiktok)\s+(?:handle|account|page)?[\s:]*([a-zA-Z0-9_]{3,})",
        r"\b[a-zA-Z0-9_]{3,30}_(?:gh|box|page|shop|store|brand|beauty|feminine)\b",
        r"\b(?:naturalbeauty)[a-zA-Z0-9_.-]{1,30}\b",
        r"(?:facebook|instagram|fb)\.com/[a-zA-Z0-9_.-]+",
        r"\b(?:box|page|shop|store|brand)[\s]*(?:gh|ng|uk|us|au)\b",
    ]
    cta_regex = re.compile("|".join(cta_patterns), re.IGNORECASE)
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
            detected_ctas.append({
                "text": cleaned_text,
                "type": "textual_intent",
                "coordinates": {"top_left": top_left, "bottom_right": bottom_right},
                "coordinates_str": f"[x: {top_left[0]}, y: {top_left[1]}]"
            })

    total_regions = len(all_extracted_elements)
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
