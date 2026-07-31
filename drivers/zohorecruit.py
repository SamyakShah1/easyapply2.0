import os
import asyncio
from datetime import datetime

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [Zoho Recruit Driver] {msg}", flush=True)

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

async def apply_zohorecruit(page, context, profile):
    log(f"Starting Zoho Recruit automation on: {page.url}")
    
    # 1. Check if we need to click the initial "I'm interested" / "Apply" button
    interest_btn = await page.query_selector(
        "//button[contains(text(), \"I'm interested\") or contains(text(), \"I'm Interested\") or contains(text(), \"Apply\") or contains(text(), \"Apply Now\")] | "
        "//a[contains(text(), \"I'm interested\") or contains(text(), \"I'm Interested\") or contains(text(), \"Apply\") or contains(text(), \"Apply Now\")]"
    )
    if interest_btn and await interest_btn.is_visible():
        log("Found interest button. Clicking it to reveal the application form...")
        await interest_btn.click()
        await page.wait_for_timeout(4000)
        
    # 2. Fill basic details
    label_mappings = {
        "First Name": profile.get("first_name", profile["full_name"].split()[0]),
        "Last Name": profile.get("last_name", profile["full_name"].split()[-1] if len(profile["full_name"].split()) > 1 else ""),
        "Email": profile["email"],
        "Mobile": profile["phone_number"],
        "Phone": profile["phone_number"],
        "City": profile["current_location"],
        "Location": profile["current_location"],
        "LinkedIn": profile.get("linkedin_url", ""),
        "GitHub": profile.get("github_url", "")
    }
    
    labels = await page.query_selector_all("label")
    for label in labels:
        try:
            text = await label.inner_text()
            text = text.replace("*", "").strip()
            
            if text in label_mappings:
                id_attr = await label.get_attribute("id")
                if id_attr and id_attr.startswith("crc-label-"):
                    input_name = id_attr.replace("crc-label-", "")
                    input_el = await page.query_selector(f"input[name='{input_name}']")
                    if input_el and await input_el.is_visible():
                        success = await robust_fill(input_el, label_mappings[text])
                        if success:
                            log(f"Filled {text} ({input_name}) -> {label_mappings[text]}")
                        await page.wait_for_timeout(500)
        except Exception:
            pass
            
    # 3. Upload Resume
    resume_input = await page.query_selector("input[type='file'][id*='resume'], input[type='file'][id*='file'], input[type='file']")
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
        {"selector": "input[id*='LinkedIn'], input[name*='LinkedIn'], input[id*='linkedin']", "value": profile.get("linkedin_url", "")},
        {"selector": "input[id*='GitHub'], input[name*='GitHub'], input[id*='github']", "value": profile.get("github_url", "")}
    ]
    for wf in web_fields:
        el = await page.query_selector(wf["selector"])
        if el and await el.is_visible():
            await robust_fill(el, wf["value"])
            log(f"Filled link {wf['selector']} -> {wf['value']}")
            await page.wait_for_timeout(500)

    # 4. Check for Submit button
    submit_btn = await page.query_selector("input[type='button'][value*='Submit'], button[id*='submit'], button:has-text('Submit'), input[type='submit']")
    if submit_btn:
        log("Found submit button.")
        
    log("Form filled. Waiting 3 seconds for visual check before returning...")
    await page.wait_for_timeout(3000)
    return True
