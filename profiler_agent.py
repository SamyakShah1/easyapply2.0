import os
import json
import sqlite3
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("profiler_agent") or os.getenv("all_other")
DB_PATH = "job_hunter.db"
PROFILE_FILE = "raw_profile.txt"

async def extract_preferences():
    if not GROQ_API_KEY:
        print("[!] No 'profiler_agent' or 'all_other' key found in .env.")
        return
        
    if not os.path.exists(PROFILE_FILE):
        print(f"[!] Please create a '{PROFILE_FILE}' file and paste your resume, salary expectations, and preferred locations into it.")
        # Create a template file for the user
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            f.write("Please paste your resume and preferences here.\nExample: I am a senior python dev looking for remote jobs or bangalore. I want at least 20 LPA.")
        return
        
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read().strip()
        
    if not raw_text or raw_text.startswith("Please paste your resume"):
        print(f"[!] '{PROFILE_FILE}' is empty or contains the template. Please fill it with your details and run this again.")
        return
        
    print(f"Analyzing {PROFILE_FILE} to build your Agent State...")
    
    prompt = f"""
    You are the Profiler Agent. Your job is to extract highly specific job hunting preferences from the user's unstructured text/resume.
    
    User's Raw Profile/Input:
    \"\"\"
    {raw_text}
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
                timeout=20.0
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            # Save to Database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Update the single configuration row
            cursor.execute('''
            UPDATE user_preferences 
            SET target_roles = ?, min_salary = ?, locations = ?, skills = ? 
            WHERE id = (SELECT id FROM user_preferences LIMIT 1)
            ''', (result["target_roles"], result["min_salary"], result["locations"], result["skills"]))
            
            conn.commit()
            conn.close()
            
            print("\n✅ Profiler Agent successfully updated your State Database!")
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(f"Failed to profile user: {e}")

if __name__ == "__main__":
    asyncio.run(extract_preferences())
