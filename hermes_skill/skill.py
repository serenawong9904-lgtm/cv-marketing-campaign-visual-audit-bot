# =====================================================================
# MEMBER 4: THE ARCHITECT (HERMES SKILL INTEGRATION)
# =====================================================================
import json
import requests
import yaml
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None
    print("⚠️ python-dotenv not installed; environment variables will still be read from the shell.")

# --- SKILL METADATA (For OpenRouter / Hermes Platform) ---
SKILL_NAME = "Marketing Campaign Visual Audit Skill"
TARGET_USER = "Marketing, business, communication students"
REAL_WORLD_PROBLEM = "Evaluating the design effectiveness of promotional materials (posters, banners, social media ads) is often subjective and manual. Students and marketers need an automated way to assess readability, CTA strength, and platform suitability."
INPUT_FORMAT = "JSON or YAML payload containing OCR text, bounding boxes, and visual quality metrics (brightness, blur)."
CV_IMAGE_PROCESSING_METHOD = "OCR to extract poster text; color and contrast analysis; layout analysis; image quality assessment."
STEP_BY_STEP_WORKFLOW = "1. Receive OCR payload. 2. Parse text and bounding boxes. 3. Feed data to LLM with marketing audit prompt. 4. Generate structured Markdown report. 5. Generate JSON blueprint for chart generation."
OUTPUT_FORMAT = "Markdown formatted Campaign Audit Report + Python data blueprint for Member 5."
LIMITATION_HANDLING = "If OCR confidence is low or cursive fonts are detected, the report includes a disclaimer about potential text inaccuracies."
ETHICAL_BOUNDARY = "The skill only analyzes layout, text, and visual clarity. It does not judge the moral or ethical nature of the promotional content itself."

# --- API CONNECTION SECRETS ---
# 🚨 USER ACTION REQUIRED: Set your OpenRouter API Key in your environment or .env file.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_KEY_AVAILABLE = bool(OPENROUTER_API_KEY)
OPENROUTER_MODEL = "google/gemini-2.0-flash-exp:free"

def generate_audit_report(yaml_data):
    """
    Sends the parsed YAML data to OpenRouter (Gemini Flash) to generate the audit report.
    """
    # Load the system prompt from prompt.txt
    prompt_path = Path(__file__).parent / "prompt.txt"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        return "❌ Error: Could not find prompt.txt in the hermes_skill folder."

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/serenawong9904-lgtm/cv-marketing-campaign-visual-audit-bot/tree/telegram-quality-assessment", # Required by OpenRouter for some free keys
        "X-Title": "Visual Auditor Bot",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Here is the OCR payload to analyze:\n\n{yaml_data}"
            }
        ]
    }

    if not OPENROUTER_KEY_AVAILABLE:
        return "❌ Error: OpenRouter API key is missing. Set OPENROUTER_API_KEY in a .env file or your shell environment."

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload)
        )
        response.raise_for_status()
        
        response_json = response.json()
        
        # Parse the OpenRouter/OpenAI standard response format
        if 'choices' in response_json and len(response_json['choices']) > 0:
             return response_json['choices'][0]['message']['content']
        else:
            return f"❌ Unexpected response format from OpenRouter:\n{json.dumps(response_json, indent=2)}"
            
    except Exception as e:
        return f"❌ Error communicating with OpenRouter: {str(e)}\n\n(Did you update OPENROUTER_API_KEY in skill.py?)"


def member3_compile_report(ocr_payload):
    """
    Handoff function called from quality_assessment.py.
    Formats the OCR payload into a readable YAML string, then triggers the OpenRouter LLM.
    """
    # Convert the raw dictionary into a clean YAML string for the LLM to read easily
    yaml_formatted_data = yaml.dump(ocr_payload, default_flow_style=False, sort_keys=False)
    
    print("🚀 Triggering Member 4 Hermes Skill via OpenRouter...")
    
    # Call OpenRouter API
    markdown_report = generate_audit_report(yaml_formatted_data)
    
    return markdown_report