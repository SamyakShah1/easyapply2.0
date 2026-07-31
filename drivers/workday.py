import os
import asyncio
from datetime import datetime
import json

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [Workday Driver] {msg}", flush=True)

async def robust_fill(page, selector, val):
    try:
        await page.wait_for_selector(selector, timeout=3000)
        el = await page.query_selector(selector)
        await el.scroll_into_view_if_needed()
        await el.click(timeout=1000)
        await el.fill("")
        await el.type(str(val), delay=15)
        return True
    except Exception:
        return False

async def click_next(page):
    log("Looking for Next/Save/Continue button...")
    btn = await page.query_selector("button[data-automation-id='bottom-navigation-next-button'], button:has-text('Save and Continue'), button:has-text('Next')")
    if btn:
        await btn.scroll_into_view_if_needed()
        await btn.click()
        await page.wait_for_timeout(4000)
        return True
    return False

async def handle_account_creation(page, profile):
    log("Handling Workday Account Creation / Login...")
    
    apply_btn = await page.query_selector("a[data-automation-id='applyManually'], button:has-text('Apply Manually'), a[data-automation-id='autofillWithResume']")
    if apply_btn:
        await apply_btn.click()
        await page.wait_for_timeout(4000)

    # Check if we are on login page
    create_account_link = await page.query_selector("div[data-automation-id='createAccountLink'], a:has-text('Create Account')")
    if create_account_link:
        log("Clicking Create Account...")
        await create_account_link.click()
        await page.wait_for_timeout(3000)
        
        email = profile.get("email")
        password = "EasyApply123!@#"
        
        await robust_fill(page, "input[data-automation-id='email']", email)
        await robust_fill(page, "input[data-automation-id='password']", password)
        await robust_fill(page, "input[data-automation-id='verifyPassword']", password)
        
        checkbox = await page.query_selector("input[type='checkbox']")
        if checkbox:
            await checkbox.click(force=True)
            
        create_btn = await page.query_selector("div[data-automation-id='createAccountSubmitButton'], button:has-text('Create Account')")
        if create_btn:
            await create_btn.click()
            await page.wait_for_timeout(6000)
            log("Account created. Proceeding to application steps...")
            return True

    return False

async def apply_workday(page, context, profile):
    log(f"Starting Workday automation on: {page.url}")
    
    # Click general Apply button if present
    initial_apply = await page.query_selector("a[data-automation-id='jobFoundationalArticleApplyButton'], button:has-text('Apply')")
    if initial_apply:
        await initial_apply.click()
        await page.wait_for_timeout(4000)
        
    await handle_account_creation(page, profile)
    
    # We are inside the multi-step form. Loop until we find Submit.
    for step in range(6):
        log(f"Processing application step {step + 1}...")
        
        # 1. Check for Resume upload
        resume_input = await page.query_selector("input[type='file'][data-automation-id='file-upload-input-ref']")
        if resume_input:
            resume_path = profile.get("resume_pdf_path", "")
            if os.path.exists(resume_path):
                await resume_input.set_input_files(resume_path)
                log("Uploaded resume.")
                await page.wait_for_timeout(3000)

        # 2. Try filling standard text inputs
        fields = [
            {"selector": "input[data-automation-id='legalNameSection_firstName']", "val": profile.get("first_name", profile["full_name"].split()[0])},
            {"selector": "input[data-automation-id='legalNameSection_lastName']", "val": profile.get("last_name", profile["full_name"].split()[-1])},
            {"selector": "input[data-automation-id='addressSection_addressLine1']", "val": profile.get("current_location", "123 Main St")},
            {"selector": "input[data-automation-id='addressSection_city']", "val": profile.get("current_location", "Metropolis")},
            {"selector": "input[data-automation-id='contactInformationPage_phone_number']", "val": profile.get("phone_number", "")},
        ]
        
        for f in fields:
            el = await page.query_selector(f["selector"])
            if el and await el.is_visible():
                await robust_fill(page, f["selector"], f["val"])
                
        # 3. Handle Workday's custom Dropdowns (searchable selects)
        # Often data-automation-id="selectWidget" or similar
        # Since this is MVP, we will try to fill the minimum required and click next.
        # If it throws an error, the agent will pause for human intervention before next.

        # 4. Handle Human Verification
        verification_iframe = await page.query_selector("iframe[src*='cloudflare'], iframe[src*='recaptcha']")
        if verification_iframe:
            log("CAPTCHA detected on Workday! Waiting 45 seconds for manual solve...")
            await page.wait_for_timeout(45000)
            
        # 5. Check if it's the Submit page
        submit_btn = await page.query_selector("button[title='Submit'], button:has-text('Submit'), button[data-automation-id='bottom-navigation-submit-button']")
        if submit_btn:
            log("Submit button found! Waiting 3 seconds for visual check before returning...")
            await page.wait_for_timeout(3000)
            return True
            
        # 6. Click Next
        if not await click_next(page):
            log("No Next button found. We might be done or stuck.")
            break

    return False
