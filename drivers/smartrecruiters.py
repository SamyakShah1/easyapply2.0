import os
import asyncio
from datetime import datetime

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [SmartRecruiters Driver] {msg}", flush=True)

async def robust_fill(element, val):
    try:
        await element.scroll_into_view_if_needed()
        await element.click(timeout=2000)
        await element.fill("")
        await element.type(str(val), delay=15)
        return True
    except Exception:
        try:
            await element.evaluate("(el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }", val)
            return True
        except Exception:
            return False

async def apply_smartrecruiters(page, context, profile):
    log(f"Starting SmartRecruiters automation on: {page.url}")
    
    # 1. Check if we need to click the initial "I'm Interested" / "Apply Now" button
    interest_btn = await page.query_selector(
        "//a[contains(text(), \"I'm interested\") or contains(text(), \"I'm Interested\") or contains(text(), \"Apply Now\") or contains(text(), \"Apply now\")] | "
        "//button[contains(text(), \"I'm interested\") or contains(text(), \"I'm Interested\") or contains(text(), \"Apply Now\") or contains(text(), \"Apply now\")]"
    )
    if interest_btn and await interest_btn.is_visible():
        log("Found initial interest button. Clicking it to open the application form...")
        await interest_btn.click()
        await page.wait_for_timeout(4000)
        
    # 2. Fill basic details
    fields = [
        {"selector": "input[id*='first-name'], input[name='firstName'], input[id='firstName']", "value": profile.get("first_name", profile["full_name"].split()[0])},
        {"selector": "input[id*='last-name'], input[name='lastName'], input[id='lastName']", "value": profile.get("last_name", profile["full_name"].split()[-1] if len(profile["full_name"].split()) > 1 else "")},
        {"selector": "input[id*='email'], input[name='email'], input[id='email']", "value": profile["email"]},
        {"selector": "input[id*='phone'], input[name='phone'], input[id='phone']", "value": profile["phone_number"]},
        {"selector": "input[id*='city'], input[id*='location'], input[name*='location']", "value": profile["current_location"]},
    ]
    
    for f in fields:
        el = await page.query_selector(f["selector"])
        if el and await el.is_visible():
            success = await robust_fill(el, f["value"])
            if success:
                log(f"Filled {f['selector']} -> {f['value']}")
            await page.wait_for_timeout(500)
            
    # 3. Upload Resume
    resume_input = await page.query_selector("input[type='file'][id*='resume'], input[type='file']")
    if resume_input:
        resume_path = profile.get("resume_pdf_path", "")
        if os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            log(f"Uploaded resume: {os.path.basename(resume_path)}")
            await page.wait_for_timeout(3000)
        else:
            log(f"Warning: Resume path not found: {resume_path}")
            
    # 4. Fill standard links (if visible)
    web_fields = [
        {"selector": "input[id*='linkedin'], input[name*='linkedin']", "value": profile.get("linkedin_url", "")},
        {"selector": "input[id*='website'], input[name*='website'], input[id*='portfolio']", "value": profile.get("portfolio_url", "")}
    ]
    for wf in web_fields:
        el = await page.query_selector(wf["selector"])
        if el and await el.is_visible():
            await robust_fill(el, wf["value"])
            log(f"Filled link {wf['selector']} -> {wf['value']}")
            await page.wait_for_timeout(500)

    # 5. Check for Submit button
    submit_btn = await page.query_selector("button[type='submit'], button[id*='submit'], button:has-text('Submit')")
    if submit_btn:
        log("Form filled. Waiting 3 seconds for visual check before returning...")
        await page.wait_for_timeout(3000)
        return True
        
    return False
