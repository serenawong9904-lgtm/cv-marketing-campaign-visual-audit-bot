# =====================================================================
# MEMBER 4: THE ARCHITECT (AI SKILL INTEGRATION)
# =====================================================================
import json
import requests
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

# Load hidden API keys from the .env file
load_dotenv()

# --- SKILL METADATA ---
# Metadata has been moved to SKILL.md per the Agent Skills specification.

# --- API CONNECTION SECRETS ---
# 🚨 USER ACTION REQUIRED: Set your OpenRouter API Key in your environment!
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "[HIDDEN_FOR_SECURITY]").strip()
OPENROUTER_KEY_AVAILABLE = OPENROUTER_API_KEY != "[HIDDEN_FOR_SECURITY]" and bool(OPENROUTER_API_KEY)
OPENROUTER_MODEL = "openrouter/free" # Use the global free model to avoid credit issues

def generate_audit_report(yaml_data):
    """
    Sends the parsed YAML data to OpenRouter (Gemini Flash) to generate the audit report.
    """
    # Load the system prompt from the markdown body of SKILL.md
    prompt_path = Path(__file__).parent.parent / "SKILL.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Extract content after the second '---' (the YAML frontmatter)
            parts = content.split('---', 2)
            if len(parts) >= 3:
                system_prompt = parts[2].strip()
            else:
                system_prompt = content.strip()
    except FileNotFoundError:
        return "❌ Error: Could not find SKILL.md in the marketing-visual-audit folder."

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
    
    print("🚀 Triggering OpenRouter AI...")
    
    # Call OpenRouter API
    markdown_report = generate_audit_report(yaml_formatted_data)
    
    return markdown_report

def generate_bot_response(user_text):
    """
    Acts as the 'Bot Response Skill' to handle general chat and commands.
    """
    if not OPENROUTER_KEY_AVAILABLE:
        return "⚠️ OpenRouter API Key is missing. I cannot chat right now."
        
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/serenawong9904-lgtm/cv-marketing-campaign-visual-audit-bot/tree/telegram-quality-assessment",
        "X-Title": "Visual Auditor Bot",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an intelligent Agentic AI managing a Marketing Campaign Visual Audit Bot. You can answer questions about the bot's status, agents, and capabilities. Keep your answers brief and helpful. If they ask to audit a poster, remind them to upload an image."
            },
            {
                "role": "user",
                "content": user_text
            }
        ]
    }

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"❌ OpenRouter Error: {response.text}"
    except Exception as e:
        return f"❌ Connection Error: {str(e)}"
