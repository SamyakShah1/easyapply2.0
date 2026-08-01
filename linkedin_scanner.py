import asyncio
import sqlite3
import json
import urllib.parse
from datetime import datetime
import os
from dotenv import load_dotenv
import httpx
from playwright.async_api import async_playwright

load_dotenv()
GROQ_API_KEY = os.getenv("linkedin_agent") or os.getenv("all_other")
DB_PATH = "job_hunter.db"

def get_preferences():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT target_roles, min_salary, locations, skills FROM user_preferences LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "target_roles": row[0],
            "min_salary": row[1],
            "locations": row[2],
            "skills": row[3]
        }
    return None

def is_job_scraped(job_url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # For linkedin, sometimes url has query params, just match by basic prefix if possible, or exact
    cursor.execute("SELECT 1 FROM scraped_jobs WHERE job_url = ?", (job_url,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_job(platform, title, company, location, salary, job_url, match_reason):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO scraped_jobs (platform, job_id, title, company, location, salary, job_url, match_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (platform, job_url, title, company, location, salary, job_url, match_reason))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

async def evaluate_job_with_groq(prefs, title, company, location, salary, description):
    if not GROQ_API_KEY:
        return {"match": True, "reason": "No Groq API Key, matched by default."}
        
    prompt = f"""
    You are an AI job filter. Evaluate this job against the candidate's preferences.
    Candidate Preferences:
    - Target Roles: {prefs['target_roles']}
    - Minimum Salary: {prefs['min_salary']} INR
    - Target Locations: {prefs['locations']}
    - Skills: {prefs['skills']}
    Job Details:
    - Title: {title}
    - Company: {company}
    - Location: {location}
    - Salary: {salary}
    - Description/Summary: {description}
    Decision Rules:
    1. If the job title/role has absolutely nothing to do with Target Roles, reject.
    2. Be slightly lenient on salary if it's not explicitly stated.
    Return JSON: {{"match": true | false, "reason": "1 sentence explanation"}}
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}, "temperature": 0.1},
                timeout=15.0
            )
            return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"Groq API Error: {e}")
        return {"match": False, "reason": "API Failure"}

async def scan_linkedin():
    prefs = get_preferences()
    if not prefs: return
    
    keywords = [k.strip() for k in prefs["target_roles"].split(",")]
    if not keywords: return
    primary_keyword = keywords[0]
    encoded_keyword = urllib.parse.quote(primary_keyword)
    
    print(f"Starting LinkedIn Scanner for role: {primary_keyword}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_keyword}&location=India&f_TPR=r86400" # Last 24 hours
        print(f"Scanning: {search_url}")
        
        try:
            await page.goto(search_url, timeout=30000)
            await page.wait_for_selector(".job-search-card", timeout=10000)
        except Exception:
            print("Failed to load search results on LinkedIn. It may require auth or captcha.")
            await browser.close()
            return
            
        raw_cards = await page.query_selector_all(".job-search-card")
        print(f"Found {len(raw_cards)} job cards on LinkedIn")
        
        for card in raw_cards:
            title_el = await card.query_selector(".base-search-card__title")
            if not title_el: continue
            
            link_el = await card.query_selector("a.base-card__full-link")
            href = await link_el.get_attribute("href") if link_el else ""
            if "?" in href: href = href.split("?")[0] # clean tracking params
            
            if not href or is_job_scraped(href): continue
            
            title = await title_el.inner_text()
            title = title.strip()
            
            company_el = await card.query_selector(".base-search-card__subtitle")
            company = await company_el.inner_text() if company_el else "Unknown Company"
            company = company.strip()
            
            loc_el = await card.query_selector(".job-search-card__location")
            location = await loc_el.inner_text() if loc_el else "India"
            location = location.strip()
            
            salary = "Not Disclosed" # LinkedIn rarely shows salary on the card preview
            
            print(f"Evaluating: {title} @ {company}")
            eval_result = await evaluate_job_with_groq(prefs, title, company, location, salary, "")
            
            if eval_result.get("match"):
                print(f"✅ MATCH: {eval_result.get('reason')}")
                save_job("LinkedIn", title, company, location, salary, href, eval_result.get('reason'))
            else:
                print(f"❌ SKIP: {eval_result.get('reason')}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scan_linkedin())
