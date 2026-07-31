import os
import json
import httpx
from datetime import datetime
import asyncio

OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "llama3.2:3b"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [Greenhouse Driver] {msg}", flush=True)

async def query_llm_for_answer(question, profile):
    prompt = f"""
You are the form-filling brain of the EasyApply Web Agent.
Answer the following recruiter question based on the candidate's profile.

Candidate Profile:
- Full Name: {profile['full_name']}
- Email: {profile['email']}
- Phone: {profile['phone_number']}
- Location: {profile['current_location']}
- Total Experience: {profile['total_experience_years']}
- Notice Period: {profile['notice_period']}
- Current CTC: {profile['current_ctc']}
- Expected CTC: {profile['expected_ctc']}
- AI Agent Experience: {profile['ai_agent_experience_months']} months
- Skills: {', '.join(profile['skills'])}
- Education Details: {profile.get('education_details', {})}
- Requires Visa Sponsorship: {profile.get('requires_visa_sponsorship', 'No')}
- Previously Employed Here: {profile.get('previously_employed_at_target', 'No')}

Recruiter Question:
"{question}"

Rules:
1. Provide ONLY a short, direct answer (1-2 sentences maximum, or a single number/word if appropriate).
2. Do not explain your reasoning or add conversational filler.
3. Be professional and accurate.
"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(OLLAMA_ENDPOINT, json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1}
            })
            if resp.status_code == 200:
                result = resp.json()
                return result["message"]["content"].strip()
    except Exception as e:
        log(f"Error querying LLM: {e}")
    return ""

async def fill_react_select(page, selector, value):
    log(f"Selecting '{value}' for React-Select dropdown {selector}...")
    try:
        await page.wait_for_selector(selector, timeout=4000)
        await page.click(selector)
        await page.wait_for_timeout(800)
        
        await page.fill(selector, "")
        await page.type(selector, value, delay=100)
        await page.wait_for_timeout(1500)
        
        # Get all options
        options = await page.query_selector_all("//div[contains(@class, 'select__option')]")
        if not options:
            options = await page.query_selector_all("//div[contains(@id, 'react-select')]")
            
        best_option = None
        for opt in options:
            text = (await opt.inner_text()).strip()
            text_lower = text.lower()
            val_lower = value.lower()
            
            if text_lower == val_lower:
                best_option = opt
                break
            elif text_lower.startswith(val_lower + " ") or text_lower.startswith(val_lower + "\n"):
                best_option = opt
                break
            elif val_lower in text_lower and not best_option:
                best_option = opt
                
        if best_option:
            await best_option.scroll_into_view_if_needed()
            await best_option.click()
            log(f"Successfully selected React-Select option '{value}'")
            await page.wait_for_timeout(500)
            return True
        else:
            log(f"React-Select option '{value}' not found in dropdown list")
            return False
    except Exception as e:
        log(f"Failed to fill React-Select for {selector}: {e}")
        return False

async def robust_fill(page, selector, val):
    try:
        await page.wait_for_selector(selector, timeout=4000)
        el = await page.query_selector(selector)
        await el.scroll_into_view_if_needed()
        
        # Auto-detect React-Select input
        cls = await el.get_attribute("class") or ""
        if "select__input" in cls:
            success = await fill_react_select(page, selector, val)
            if success:
                return True
                
        tag = await el.evaluate("el => el.tagName")
        if tag == "SELECT":
            await page.select_option(selector, value=val)
            return True
            
        await page.fill(selector, str(val))
        return True
    except Exception as e:
        log(f"Fill failed for selector {selector}: {e}")
        try:
            el = await page.query_selector(selector)
            if el:
                await el.evaluate("(el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }", val)
                return True
        except Exception as e2:
            log(f"Evaluate failed: {e2}")
            return False

async def apply_greenhouse(page, context, profile):
    log(f"Starting Greenhouse automation on: {page.url}")
    
    # Click Apply button at the top to scroll/transition down if it exists
    try:
        apply_btn = await page.query_selector("button:has-text('Apply'), a:has-text('Apply')")
        if apply_btn and await apply_btn.is_visible():
            await page.click("button:has-text('Apply')", timeout=3000)
            await page.wait_for_timeout(2000)
    except Exception:
        pass
        
    # 1. Fill basic details
    fields = [
        {"id": "#first_name", "value": profile.get("first_name", profile["full_name"].split()[0])},
        {"id": "#last_name", "value": profile.get("last_name", profile["full_name"].split()[-1] if len(profile["full_name"].split()) > 1 else "")},
        {"id": "#email", "value": profile["email"]},
        {"id": "#phone", "value": profile.get("phone_country_code", "") + " " + profile["phone_number"]},
        {"id": "#country", "value": profile.get("country", "India")},
    ]
    
    for f in fields:
        el = await page.query_selector(f["id"])
        if el and await el.is_visible():
            success = await robust_fill(page, f["id"], f["value"])
            if success:
                log(f"Filled {f['id']} -> {f['value']}")
            await page.wait_for_timeout(500)
            
    # 2. Upload Resume
    resume_input = await page.query_selector("input[type='file']#resume, input[type='file']")
    if resume_input:
        resume_path = profile.get("resume_pdf_path", "")
        if os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            log(f"Uploaded resume: {os.path.basename(resume_path)}")
            await page.wait_for_timeout(2000)
        else:
            log(f"Warning: Resume path not found: {resume_path}")
            
    # 3. Handle custom questions
    inputs = await page.query_selector_all("input[id^='question_'], textarea[id^='question_'], select[id^='question_']")
    log(f"Scanning {len(inputs)} custom Greenhouse questions...")
    for el in inputs:
        if not await el.is_visible():
            continue
            
        id_val = await el.get_attribute("id") or ""
        label_text = ""
        label_el = await page.query_selector(f"label[for='{id_val}']")
        if label_el:
            label_text = await label_el.inner_text()
            
        label_text = label_text.strip().replace("\n", " ")
        if not label_text:
            continue
            
        l_lower = label_text.lower()
        fill_val = ""
        
        if "linkedin" in l_lower:
            fill_val = profile.get("linkedin_url", "")
        elif "github" in l_lower:
            fill_val = profile.get("github_url", "")
        elif "portfolio" in l_lower:
            fill_val = profile.get("portfolio_url", "")
        else:
            # Query LLM for custom answers
            log(f"Querying LLM for custom question: '{label_text}'")
            fill_val = await query_llm_for_answer(label_text, profile)
            
            # Normalize to simple Yes/No for work-auth/sponsorship dropdown text inputs
            if "visa" in l_lower or "sponsor" in l_lower or "authorized" in l_lower or "previously been employed" in l_lower:
                if "no" in fill_val.lower():
                    fill_val = "No"
                elif "yes" in fill_val.lower():
                    fill_val = "Yes"
            
        if fill_val:
            await robust_fill(page, f"#{id_val}", fill_val)
            log(f"Filled question '{label_text[:40]}' -> '{fill_val[:40]}'")
            await page.wait_for_timeout(1000)
            
    # 4. Check for submit button
    submit_btn = await page.query_selector("button[type='submit']#submit_app, button[type='submit']")
    if submit_btn:
        log("Form filled. Waiting 3 seconds for visual check before returning...")
        await page.wait_for_timeout(3000)
        return True
        
    return False
