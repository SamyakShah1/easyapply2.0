import os
import asyncio
from datetime import datetime
import json
import urllib.request
import urllib.parse

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [Lever Driver] {msg}", flush=True)

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

async def query_llm_for_answer(question_text, profile, input_type="text", options=None):
    log(f"Querying LLM for question: '{question_text}' (type: {input_type})")
    
    prompt = f"""
    You are an AI assistant applying for jobs on behalf of the following candidate:
    {json.dumps(profile, indent=2)}
    
    The application form asks this question: "{question_text}"
    """
    
    if input_type == "radio" or input_type == "select":
        prompt += f"\nYou must choose exactly ONE of the following options: {options}\nReturn ONLY the exact text of the option you choose. Do not include any explanations."
    else:
        prompt += "\nProvide a concise and direct answer based on the candidate's profile. If it's a yes/no question, answer 'Yes' or 'No'. Return ONLY the answer string."
        
    data = json.dumps({"model": "llama3.2:3b", "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data, headers={"Content-Type": "application/json"})
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, urllib.request.urlopen, req)
        result = json.loads(response.read().decode("utf-8"))
        if "response" in result:
            return result["response"].strip()
    except Exception as e:
        log(f"Error querying LLM: {e}")
    return ""

async def apply_lever(page, context, profile):
    log(f"Starting Lever automation on: {page.url}")
    
    # 1. Click "Apply for this job" if it's the landing page
    apply_btn = await page.query_selector("a.postings-btn, button:has-text('Apply')")
    if apply_btn and await apply_btn.is_visible():
        log("Clicking 'Apply for this job' button...")
        await apply_btn.click()
        await page.wait_for_timeout(3000)

    # 2. Upload Resume
    resume_input = await page.query_selector("input[type='file'][id*='resume']")
    if resume_input:
        resume_path = profile.get("resume_pdf_path", "")
        if os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            log(f"Uploaded resume: {os.path.basename(resume_path)}")
            await page.wait_for_timeout(2000)
        else:
            log(f"Warning: Resume path not found: {resume_path}")

    # 3. Standard Fields
    standard_fields = {
        "name": profile.get("full_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone_number", ""),
        "org": profile.get("current_company", ""),
        "urls[LinkedIn]": profile.get("linkedin_url", ""),
        "urls[Portfolio]": profile.get("portfolio_url", ""),
        "urls[GitHub]": profile.get("github_url", "")
    }

    for name_attr, val in standard_fields.items():
        if val:
            el = await page.query_selector(f"input[name='{name_attr}']")
            if el and await el.is_visible():
                await robust_fill(el, val)
                log(f"Filled standard field '{name_attr}'")
                await page.wait_for_timeout(300)

    # 4. Custom Questions (Iterate through all un-filled textareas and inputs without the above names)
    custom_inputs = await page.query_selector_all("textarea, input[type='text']")
    for ci in custom_inputs:
        name = await ci.get_attribute("name")
        if name and name not in standard_fields.keys() and not (await ci.input_value()):
            # Find the label
            id_attr = await ci.get_attribute("id")
            label_text = name
            if id_attr:
                label = await page.query_selector(f"label[for='{id_attr}']")
                if label:
                    label_text = await label.inner_text()
            
            ans = await query_llm_for_answer(label_text, profile, "text")
            if ans:
                await robust_fill(ci, ans)
                log(f"Filled custom field '{label_text}' with LLM answer")
                await page.wait_for_timeout(300)

    # Custom selects
    selects = await page.query_selector_all("select")
    for select in selects:
        name = await select.get_attribute("name")
        id_attr = await select.get_attribute("id")
        label_text = name
        if id_attr:
            label = await page.query_selector(f"label[for='{id_attr}']")
            if label:
                label_text = await label.inner_text()
                
        options_els = await select.query_selector_all("option")
        options = [await o.inner_text() for o in options_els if await o.get_attribute("value")]
        
        if options:
            ans = await query_llm_for_answer(label_text, profile, "select", options)
            if ans:
                for o in options_els:
                    if (await o.inner_text()).lower() == ans.lower():
                        val = await o.get_attribute("value")
                        await select.select_option(val)
                        log(f"Selected custom dropdown '{label_text}' -> '{ans}'")
                        await page.wait_for_timeout(300)
                        break

    # 5. Handle Human Verification
    log("Checking for human verification or CAPTCHA blocks...")
    verification_iframe = await page.query_selector("iframe[src*='cloudflare'], iframe[src*='recaptcha'], iframe[title*='widget']")
    if verification_iframe:
        log("Verification widget detected! Attempting to auto-solve or pausing for manual intervention...")
        try:
            box = await verification_iframe.bounding_box()
            if box:
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await page.wait_for_timeout(3000)
        except Exception:
            pass
        log("If verification is still pending, please solve it manually in the browser window now. Waiting 45 seconds...")
        await page.wait_for_timeout(45000)

    # 6. Submit
    submit_btn = await page.query_selector("button[type='submit'], button[id='btn-submit']")
    if submit_btn:
        log("Form filled. Waiting 3 seconds for visual check before returning...")
        await page.wait_for_timeout(3000)
        return True

    return False
