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
GROQ_API_KEY = os.getenv("Groq_API_KEY")
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
    cursor.execute("SELECT 1 FROM scraped_jobs WHERE job_url = ?", (job_url,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_job(platform, title, company, location, salary, job_url, match_reason):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # job_url acts as the unique job_id for this MVP
        cursor.execute('''
        INSERT INTO scraped_jobs (platform, job_id, title, company, location, salary, job_url, match_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (platform, job_url, title, company, location, salary, job_url, match_reason))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Already exists
    conn.close()

async def evaluate_job_with_groq(prefs, title, company, location, salary, description):
    if not GROQ_API_KEY:
        print("[!] No Groq API Key found. Assuming job is a match.")
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
    2. If the location is fundamentally incompatible (and not remote), reject.
    3. Be slightly lenient on salary if it's not explicitly stated.
    
    Return a valid JSON object ONLY:
    {{
        "match": true | false,
        "reason": "1 sentence explaining why"
    }}
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
                timeout=15.0
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            return result
    except Exception as e:
        print(f"Groq API Error: {e}")
        return {"match": False, "reason": "Failed to evaluate via Groq."}

async def scan_naukri():
    prefs = get_preferences()
    if not prefs:
        print("No user preferences found in DB. Run setup_db.py first.")
        return
        
    keywords = [k.strip() for k in prefs["target_roles"].split(",")]
    print(f"Starting Naukri Scanner for keywords: {keywords}")
    
    async with async_playwright() as p:
        # Use a real browser context to avoid blocks
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        for keyword in keywords:
            encoded_keyword = urllib.parse.quote(keyword)
            # Scan only first page to keep it fast for 2hr crons
            search_url = f"https://www.naukri.com/jobs-in-india-1?k={encoded_keyword}"
            print(f"\nScanning: {search_url}")
            
            try:
                await page.goto(search_url, timeout=30000)
                await page.wait_for_selector("div.srp-jobtuple-wrapper, article.jobTuple", timeout=10000)
            except Exception as e:
                print(f"Failed to load search results: {e}")
                continue
                
            raw_cards = await page.query_selector_all("div.srp-jobtuple-wrapper, article.jobTuple")
            print(f"Found {len(raw_cards)} job cards for '{keyword}'")
            
            for card in raw_cards:
                title_el = await card.query_selector("a.title, a.job-tuple-title")
                if not title_el: continue
                href = await title_el.get_attribute("href")
                if not href: continue
                if href.startswith("/"): href = "https://www.naukri.com" + href
                
                # Instantly discard if we've already scraped it
                if is_job_scraped(href):
                    continue
                    
                title = await title_el.inner_text()
                
                company_el = await card.query_selector("a.comp-name-link, .companyName")
                company = await company_el.inner_text() if company_el else "Unknown Company"
                
                loc_el = await card.query_selector(".locWdth, .location")
                location = await loc_el.inner_text() if loc_el else "India"
                
                sal_el = await card.query_selector(".salary, .sal")
                salary = await sal_el.inner_text() if sal_el else "Not Disclosed"
                
                desc_el = await card.query_selector(".job-description, .ellipsis.job-description")
                description = await desc_el.inner_text() if desc_el else ""
                
                print(f"Evaluating: {title} @ {company}")
                eval_result = await evaluate_job_with_groq(prefs, title, company, location, salary, description)
                
                if eval_result.get("match"):
                    print(f"✅ MATCH: {eval_result.get('reason')}")
                    save_job("Naukri", title, company, location, salary, href, eval_result.get('reason'))
                else:
                    print(f"❌ SKIP: {eval_result.get('reason')}")
                    
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scan_naukri())
