import os
import json
import sqlite3
import httpx
import asyncio
import pdfplumber
import logging
from dotenv import load_dotenv

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/profiler.log", encoding='utf-8'),
        logging.StreamHandler() # Also print to terminal
    ]
)

load_dotenv()
GROQ_API_KEY = os.getenv("profiler_agent") or os.getenv("all_other")
DB_PATH = "job_hunter.db"
PROFILE_FILE = "raw_profile.txt"
JSON_PROFILE = "profile.json"

def extract_pdf_text(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logging.error(f"Error reading PDF ({pdf_path}): {e}")
        return ""

async def extract_preferences():
    if not GROQ_API_KEY:
        logging.error("No 'profiler_agent' or 'all_other' key found in .env.")
        return
        
    raw_text = ""
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
            logging.info(f"Loaded {len(raw_text)} characters from {PROFILE_FILE}")
            
    pdf_text = ""
    if os.path.exists(JSON_PROFILE):
        try:
            with open(JSON_PROFILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                pdf_path = data.get("resume_pdf_path")
                if pdf_path and os.path.exists(pdf_path):
                    logging.info(f"Extracting text from resume: {pdf_path}")
                    pdf_text = extract_pdf_text(pdf_path)
                    logging.info(f"Extracted {len(pdf_text)} characters from Resume PDF.")
                else:
                    logging.warning(f"Resume not found at path specified in profile.json: {pdf_path}")
        except Exception as e:
            logging.error(f"Could not parse profile.json: {e}")
            
    if not raw_text and not pdf_text:
        logging.error(f"No text found in {PROFILE_FILE} and no valid resume PDF found.")
        return
        
    logging.info("Analyzing your Profile and Resume via Groq 70B AI...")
    
    prompt = f"""
    You are the Profiler Agent. Your job is to extract highly specific job hunting preferences from the user's unstructured text and resume.
    
    User's Raw Profile Input:
    \"\"\"
    {raw_text}
    \"\"\"
    
    User's Resume Content:
    \"\"\"
    {pdf_text}
    \"\"\"
    
    You must extract and output a valid JSON object with the following schema:
    {{
        "target_roles": "Comma-separated string of the 3 most ideal job titles (e.g. 'Backend Engineer, AI Developer, Python Lead')",
        "min_salary": integer representing the absolute minimum acceptable salary in INR per year (e.g. 1500000). If not specified, estimate based on experience or default to 500000,
        "locations": "Comma-separated string of desired locations (e.g. 'Remote, Bangalore, Mumbai')",
        "skills": "Comma-separated string of their top 5 core technical skills (e.g. 'Python, FastAPI, AWS, Docker')"
    }}
    
    Respond ONLY with the JSON object. Do not wrap in markdown blocks.
    """
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                },
                timeout=30.0
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE user_preferences 
            SET target_roles = ?, min_salary = ?, locations = ?, skills = ? 
            WHERE id = (SELECT id FROM user_preferences LIMIT 1)
            ''', (result["target_roles"], result["min_salary"], result["locations"], result["skills"]))
            conn.commit()
            conn.close()
            
            logging.info("✅ Profiler Agent successfully updated your State Database based on your Resume!")
            logging.info("\n=== EXTRACTED AI PROFILE ===")
            logging.info(json.dumps(result, indent=4))
            logging.info("============================")
            
    except Exception as e:
        logging.error(f"Failed to profile user: {e}")

if __name__ == "__main__":
    asyncio.run(extract_preferences())
