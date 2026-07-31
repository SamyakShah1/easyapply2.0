import os
import asyncio
from datetime import datetime
import json
import urllib.request
import urllib.parse

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print(f"[{timestamp}] [Generic LLM Driver] {msg}", flush=True)

async def robust_fill(page, element, val):
    try:
        await element.scroll_into_view_if_needed()
        
        tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
        el_type = await element.evaluate("el => el.type ? el.type.toLowerCase() : ''")
        
        if tag_name == "input" and el_type in ["radio", "checkbox"]:
            # For radios/checkboxes, we click if it matches
            await element.click(force=True)
            return True
        elif tag_name == "select":
            # Select option
            options = await element.query_selector_all("option")
            for o in options:
                if val.lower() in (await o.inner_text()).lower():
                    opt_val = await o.get_attribute("value")
                    await element.select_option(opt_val)
                    return True
            return False
        else:
            # Text input or textarea
            await element.click(timeout=2000)
            await element.fill("")
            await element.type(str(val), delay=15)
            return True
    except Exception as e:
        log(f"Error robustly filling element: {e}")
        return False

async def parse_dom_and_fill(page, profile):
    log("Scanning DOM for generic input fields...")
    
    # 1. Grab all relevant input fields
    inputs = await page.query_selector_all("input:not([type='hidden']):not([type='file']):not([type='submit']):not([type='button']), textarea, select")
    
    if not inputs:
        log("No input fields found to parse.")
        return False
        
    form_fields = []
    element_map = {}
    
    for i, el in enumerate(inputs):
        try:
            is_visible = await el.is_visible()
            if not is_visible: continue
            
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            name = await el.get_attribute("name") or ""
            id_attr = await el.get_attribute("id") or ""
            ph = await el.get_attribute("placeholder") or ""
            
            # Try to find a label
            label_text = name or id_attr or ph
            if id_attr:
                lbl = await page.query_selector(f"label[for='{id_attr}']")
                if lbl:
                    label_text = await lbl.inner_text()
                    
            if not label_text.strip():
                label_text = f"Unknown Field {i}"
                
            field_id = f"field_{i}"
            element_map[field_id] = el
            
            field_data = {
                "field_id": field_id,
                "label": label_text.strip(),
                "type": tag
            }
            
            if tag == "select":
                opts = await el.query_selector_all("option")
                opt_texts = [await o.inner_text() for o in opts if await o.get_attribute("value")]
                field_data["options"] = opt_texts
                
            form_fields.append(field_data)
        except Exception:
            pass

    if not form_fields:
        log("No visible valid fields found.")
        return False

    log(f"Found {len(form_fields)} fields. Querying LLM to map profile data...")
    
    prompt = f"""
    You are an AI assistant automating a job application.
    Candidate Profile: {json.dumps(profile)}
    
    Here is a list of form fields extracted from the webpage:
    {json.dumps(form_fields, indent=2)}
    
    Map the candidate's profile to the form fields.
    If a field asks for something not in the profile, answer 'N/A' or make a logical deduction based on the profile.
    If it's a select field, you MUST choose exactly one of the options provided.
    
    Return ONLY a valid JSON object where the keys are the `field_id` and the values are the strings to fill in. 
    Do not include markdown blocks or any other text.
    """
    
    data = json.dumps({"model": "llama3.2:3b", "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data, headers={"Content-Type": "application/json"})
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, urllib.request.urlopen, req)
        result = json.loads(response.read().decode("utf-8"))
        if "response" in result:
            llm_text = result["response"].strip()
            # Clean up potential markdown formatting
            if llm_text.startswith("```json"):
                llm_text = llm_text[7:]
            if llm_text.endswith("```"):
                llm_text = llm_text[:-3]
                
            mapping = json.loads(llm_text.strip())
            
            log(f"Received LLM mapping: {mapping}")
            
            for f_id, val in mapping.items():
                if f_id in element_map and str(val).lower() != "n/a" and str(val).strip():
                    await robust_fill(page, element_map[f_id], val)
                    log(f"Filled {f_id} -> {val}")
                    await page.wait_for_timeout(300)
                    
    except Exception as e:
        log(f"Error querying LLM or parsing response: {e}")

    # Handle resume file
    resume_input = await page.query_selector("input[type='file']")
    if resume_input:
        resume_path = profile.get("resume_pdf_path", "")
        if os.path.exists(resume_path):
            await resume_input.set_input_files(resume_path)
            log("Uploaded resume.")
            await page.wait_for_timeout(2000)

    # Human Verification
    verification_iframe = await page.query_selector("iframe[src*='cloudflare'], iframe[src*='recaptcha'], iframe[title*='widget']")
    if verification_iframe:
        log("CAPTCHA detected! Waiting 45 seconds for manual solve...")
        await page.wait_for_timeout(45000)

    # Try to find submit
    submit_btn = await page.query_selector("button[type='submit'], button:has-text('Submit'), button:has-text('Apply')")
    if submit_btn:
        log("Submit button found! Waiting 3 seconds for visual check...")
        await page.wait_for_timeout(3000)
        return True

    return False

async def apply_generic(page, context, profile):
    log(f"Starting Generic LLM fallback on: {page.url}")
    return await parse_dom_and_fill(page, profile)
