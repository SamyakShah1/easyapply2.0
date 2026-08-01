import asyncio
import json
import os
import subprocess
import socket
import sys
from playwright.async_api import async_playwright
import httpx
from datetime import datetime

# Add autoapply root to path so tracker is importable when run as subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tracker

# Force UTF-8 stdout on Windows (prevents charmap codec crash from Unicode job titles)
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Local Ollama configuration
OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:3b"

# Global logger helper — writes to internshala.log for the orchestrator
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    formatted_msg = f"[{timestamp}] {message}"
    # Safe print: replace any unencodable chars instead of crashing
    print(formatted_msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)

    os.makedirs("logs", exist_ok=True)
    with open("logs/internshala.log", "a", encoding="utf-8", errors="replace") as f:
        f.write(formatted_msg + "\n")

# Helper to check if Chrome is already running
def is_chrome_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', 9222)) == 0

# Helper to launch Chrome
def launch_chrome():
    if is_chrome_running():
        log("[Chrome] Debugging instance is already running. Attaching...")
        return
        
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\chrome-dev-profile"
    
    log(f"[Chrome] Launching Chrome dynamically: {chrome_path}")
    
    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    log("[Chrome] Waiting 3 seconds for Chrome to initialize...")

# Robust Click Helper
async def robust_click(element, page):
    try:
        await element.scroll_into_view_if_needed()
        await element.click(timeout=3000)
        return True
    except Exception:
        log("   └─ [Robust Click] Pointer click blocked. Falling back to JavaScript click...")
        try:
            await element.evaluate("el => el.click()")
            return True
        except Exception as js_err:
            log(f"   └─ [Robust Click Failed] JavaScript click failed: {js_err}")
            return False

# Robust Fill Helper (Supports Input, Select Dropdowns, and ContentEditable elements)
async def robust_fill(element, val):
    val = str(val)
    try:
        await element.scroll_into_view_if_needed()
        tag = await element.evaluate("el => el.tagName")
        content_editable = await element.get_attribute("contenteditable") or ""
        
        if content_editable.lower() == "true":
            # Direct innerText assign for contenteditable elements
            await element.evaluate("(el, value) => { el.innerText = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }", val)
            return True
            
        if tag == "SELECT":
            log(f"   └─ [Selection dropdown] Selecting option '{val}'...")
            await element.select_option(value=val)
            return True
            
        # Standard input fill
        try:
            await element.click(timeout=2000)
        except Exception:
            await element.evaluate("el => el.focus()")
        await element.fill("")
        await element.type(val, delay=20)
        return True
    except Exception as e:
        log(f"   └─ [Robust Fill Fallback] Typing failed, trying direct value assign: {e}")
        try:
            tag = await element.evaluate("el => el.tagName")
            content_editable = await element.get_attribute("contenteditable") or ""
            if content_editable.lower() == "true":
                await element.evaluate("(el, value) => { el.innerText = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }", val)
            elif tag == "SELECT":
                await element.evaluate("(el, value) => { el.value = value; el.dispatchEvent(new Event('change')); }", val)
            else:
                await element.evaluate("(el, value) => { el.value = value; }", val)
            return True
        except Exception as assign_err:
            log(f"   └─ [Robust Fill Failed]: {assign_err}")
            return False

# Robust local Ollama API call wrapper (with JSON formatting)
async def robust_ollama_api_call(messages, timeout=60.0):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                OLLAMA_ENDPOINT,
                json=payload,
                timeout=timeout
            )
            if response.status_code == 200:
                res_data = response.json()
                content = res_data["message"]["content"]
                return json.loads(content)
            else:
                raise Exception(f"Ollama HTTP {response.status_code}: {response.text}")
        except Exception as e:
            log(f"[Ollama Error] Call failed: {e}")
            raise e

# Helper to pre-screen a single batch of 10 cards dynamically
async def pre_screen_single_batch(batch_cards, profile):
    cards_text = ""
    for card in batch_cards:
        cards_text += f"Index: {card['index']} | Title: '{card['title']}' | Company: '{card['company']}' | Details: '{card['summary']}'\n"
        
    prompt = f"""
You are the pre-screening filter of the EasyApply Autonomous Job Agent.
Analyze the following list of job cards and decide which ones match the candidate's specific goals.
You must disqualify roles that do NOT align with the candidate's desired role area, or have salary ranges lower than candidate expectations, to save browser loading time.

Candidate Job Search Goals & Preferences:
{profile.get('target_job_description', '')}

Candidate Profile Details:
- Expected CTC: {profile['expected_ctc']} INR per year
- Experience: {profile['total_experience_years']}

Job Cards to evaluate:
{cards_text}

Decision Rules:
- Set match = true only for jobs that match the candidate's target job description (e.g., if candidate wants HR, match HR; if candidate wants SDE, match SDE).
- Set match = false for mismatching fields or roles that have salaries significantly below candidate expectations.

Return your decision ONLY as a valid JSON object listing the qualified indices to visit:
{{
  "qualified_indices": [number, number, ...]
}}
"""
    messages = [{"role": "user", "content": prompt}]
    res = await robust_ollama_api_call(messages)
    return res.get("qualified_indices", [])

# Agentic Search Card Pre-Screener (Batched execution in groups of 10 for 100% accuracy)
async def pre_screen_job_cards(cards, profile):
    batch_size = 10
    batches = [cards[i:i + batch_size] for i in range(0, len(cards), batch_size)]
    
    qualified_indices = []
    log(f"[AI Pre-Screener] Batching screening of {len(cards)} jobs into {len(batches)} groups using local Ollama...")
    
    for idx, batch in enumerate(batches):
        try:
            log(f"   └─ Screening batch {idx+1}/{len(batches)} (Cards {batch[0]['index']} to {batch[-1]['index']})...")
            batch_qualified = await pre_screen_single_batch(batch, profile)
            qualified_indices.extend(batch_qualified)
            
            # Throttle slightly to keep CPU usage stable
            await asyncio.sleep(1.0)
        except Exception as e:
            log(f"   └─ Batch {idx+1} screening failed: {e}")
            qualified_indices.append(batch[0]["index"])
            
    log(f"[AI Pre-Screener Completed] Selected Card Indices to visit: {qualified_indices}")
    return qualified_indices

# Query local Ollama to check if the job description matches preferences dynamically
async def check_job_match(title, company, description, salary, location, profile):
    prompt = f"""
You are the screening system for the EasyApply Autonomous Job Agent.
Analyze the following job details and decide if it matches the candidate's specific job preferences.

Candidate Job Search Goals & Preferences:
{profile.get('target_job_description', '')}

Candidate Profile Details:
- Skills: {', '.join(profile['skills'])}
- Experience: {profile['total_experience_years']}
- Expected CTC: {profile['expected_ctc']} INR per year

Scraped Job Details:
- Title: {title}
- Company: {company}
- Salary Range: {salary}
- Location: {location}
- Description: {description}

Strict Decision Rules:
1. Reject (match = false) if the maximum Salary Range is less than the Candidate's Expected CTC (e.g. if expected is 10 LPA and salary range is 3-6 LPA, it is a mismatch).
2. Reject (match = false) if the job requires significantly more experience than the candidate has.
3. Set match = true only if the role field, technology/domain stack, salary range, and locations align with the candidate's specific preferences.

Return your decision ONLY as a valid JSON object matching this structure:
{{
  "match": true | false,
  "reasoning": "A 1-sentence explanation of why it is a match or mismatch based on their preferences"
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        res = await robust_ollama_api_call(messages)
        log(f"AI Filter Result for '{title}' @ '{company}': Match={res['match']} | Reason: {res.get('reasoning', '')}")
        return res
    except Exception as e:
        log(f"[AI Matcher Failed] Mismatch defaulted for safety. Error: {e}")
        
    return {"match": False, "reasoning": "Error checking fit. Skipped job for safety."}

# Query local Ollama to decide form filling
async def get_llm_action_decision(url, title, elements, profile, chat_history=""):
    elements_text = ""
    for el in elements:
        editable_status = "Yes" if el["editable"] else "No"
        options_str = f" | Options: {el['options']}" if el['options'] else ""
        elements_text += (
            f"Index: {el['index']} | Tag: {el['tag']} | Label: '{el['label']}' | "
            f"ID: '{el['id']}' | Class: '{el['class']}' | Placeholder: '{el['placeholder']}' | "
            f"Type: '{el['type']}' | Editable: {editable_status}{options_str}\n"
        )
        
    prompt = f"""
You are the form-filling brain of the EasyApply Web Agent.
Decide the next action to take to apply for the job.

Candidate Details:
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
- Cover Letter Pitch: {profile['cover_letter_pitch']}
- Education Details: {profile.get('education_details', {})}

Page Context:
- URL: {url}
- Title: {title}

{"- Recent Chatbot / Recruiter Chat Message History:" if chat_history else ""}
{chat_history if chat_history else ""}

Visible elements:
{elements_text}

Rules:
1. If you see a recommendation modal (e.g., job suggestions with a 'Skip' button and an 'Apply now' button for another job), this means the primary application was ALREADY completed. Choose DONE.
2. If you see a success modal/popup, choose DONE.
3. If there is a form visible:
   - Fill in standard profile fields matching candidate details.
   - If the form asks for 10th percentage, 12th percentage, graduation CGPA/percentage, branch, or year, use the details provided in "Education Details". Do NOT write "None" if the value exists in Education Details!
   - For custom text questions, write a professional 2-sentence response.
   - For custom experience numeric questions, fill in "{profile['ai_agent_experience_months']}".
   - If there is a file input, UPLOAD the resume.
   - After filling form, click the submit/apply button.
4. IMPORTANT CHATBOT / RECRUITER DIALOG RULE:
   - If you see a Chatbot interface (messages on the screen asking questions like "SSLC Marks", "10th percentage", etc.), inspect the "Recent Chatbot / Recruiter Chat Message History" to find the LATEST question.
   - Type your answer to that question into the editable text area or input box (usually Index 0) and choose action_type "FILL".
   - Once the text box is filled, in the NEXT step click the "Save" or "Send" button (usually the DIV or button with label "Save" or class containing "send" or "btn"). Do NOT select DONE until the application completes successfully.
5. IMPORTANT: You MUST ONLY choose "action_type": "FILL" for elements marked as "Editable: Yes".
6. For SELECT elements, choose "action_type": "FILL" and specify the exact matching VALUE option string in the "fill_value" field from the available Options list.
7. For clicking buttons, links, selecting radios/checkboxes, or submitting forms, choose "action_type": "CLICK".
8. Return ONLY a JSON object:
{{
  "reasoning": "Explanation",
  "action_type": "CLICK" | "FILL" | "UPLOAD" | "DONE",
  "target_index": number,
  "fill_value": "string" (value to type or select value if dropdown or file path if upload)
}}
"""
    messages = [{"role": "user", "content": prompt}]
    return await robust_ollama_api_call(messages)

# The state-machine loop that handles form navigation
async def execute_application_flow(page, context, profile):
    for step in range(1, 6):
        url = page.url
        title = await page.title()
        log(f"   └─ [Sub-step {step}] URL: {url}")
        
        # Take a visual log screenshot
        artifact_dir = r"C:\Users\Samyak Shah\autoapply"
        screenshot_path = os.path.join(artifact_dir, f"autopilot_step_{step}.png")
        try:
            await page.screenshot(path=screenshot_path)
        except Exception:
            pass
            
        # Scope to modal if visible
        modal_selectors = ["#application-form-container", "div[role='dialog']", ".modal-dialog", ".chatbot_Drawer", "[class*='drawer']", "[class*='chatbot']"]
        active_modal = None
        for sel in modal_selectors:
            modal_elements = await page.query_selector_all(sel)
            for m_el in modal_elements:
                if await m_el.is_visible():
                    active_modal = m_el
                    break
            if active_modal:
                break
                
        if active_modal:
            log(f"   └─ Detected open modal dialog. Scoping interactive elements inside it.")
            raw_elements = await active_modal.query_selector_all("input, textarea, button, a.proceed-cta, a.apply, [contenteditable='true']")
        else:
            raw_elements = await page.query_selector_all("input, textarea, button, a.proceed-cta, a.apply, [contenteditable='true']")
            
        elements = []
        for idx, el in enumerate(raw_elements):
            try:
                if await el.is_visible():
                    tag = await el.evaluate("el => el.tagName")
                    id_val = await el.get_attribute("id") or ""
                    class_val = await el.get_attribute("class") or ""
                    placeholder = await el.get_attribute("placeholder") or await el.get_attribute("data-placeholder") or ""
                    el_type = await el.get_attribute("type") or ""
                    text = await el.inner_text() or ""
                    text = text.strip().replace("\n", " ")
                    if tag == "A" and not text:
                        continue
                        
                    # 1. Classify if element is editable (input/textarea fields)
                    is_editable = False
                    content_editable = await el.get_attribute("contenteditable") or ""
                    if tag in ["INPUT", "TEXTAREA", "SELECT"] or content_editable.lower() == "true":
                        if el_type.lower() not in ["radio", "checkbox", "button", "submit", "file"]:
                            is_editable = True
                            
                    # 2. Contextual DOM Label Extractor (Retrieves exact question labels for inputs)
                    label = await el.evaluate("""
                        el => {
                            if (el.id) {
                                let label = document.querySelector(`label[for="${el.id}"]`);
                                if (label && label.innerText.trim()) return label.innerText.trim();
                            }
                            let container = el.closest('.form-row, .form-group, .question-container, .question, li, td, tr, div');
                            if (container) {
                                let labelEl = container.querySelector('label, .label, .question, .q-text, span.title, p.title');
                                if (labelEl && labelEl.innerText.trim()) return labelEl.innerText.trim();
                                let text = container.innerText.trim();
                                if (text && text.length < 150) {
                                    return text.split('\\n')[0].trim();
                                }
                            }
                            return "";
                        }
                    """)
                    if not label:
                        if is_editable:
                            label = placeholder or id_val or class_val
                        else:
                            label = text or placeholder or id_val or class_val
                        
                    # 3. Dropdown options parsing
                    options = []
                    if tag == "SELECT":
                        opt_elements = await el.query_selector_all("option")
                        for opt in opt_elements:
                            val = await opt.get_attribute("value") or ""
                            txt = await opt.inner_text() or ""
                            if txt.strip():
                                options.append(f"{val}:{txt.strip()}")
                                
                    elements.append({
                        "index": idx, "tag": tag, "id": id_val, "class": class_val,
                        "text": text[:100], "placeholder": placeholder[:100], "type": el_type,
                        "label": label[:150], "options": options, "editable": is_editable, "handle": el
                    })
            except Exception:
                pass
                
        # Extract chat message history if a chatbot drawer is open
        chat_history = ""
        if active_modal:
            try:
                msg_elements = await active_modal.query_selector_all(".chatbot_MessageContainer .msg, .chatbot_MessageContainer .botMsg, .chatbot_MessageContainer .userMsg, .botMsg, .userMsg, .msg")
                msgs = []
                for m in msg_elements:
                    if await m.is_visible():
                        t = await m.inner_text()
                        if t.strip():
                            msgs.append(t.strip())
                if msgs:
                    # Keep the last 5 messages
                    chat_history = "\n".join(msgs[-5:])
            except Exception:
                pass

        if not elements:
            await page.wait_for_timeout(2000)
            continue
            
        try:
            decision = await get_llm_action_decision(url, title, elements, profile, chat_history=chat_history)
        except Exception as api_err:
            log(f"   └─ Error: LLM decision action failed: {api_err}")
            return False
            
        action_type = decision["action_type"]
        target_idx = decision["target_index"]
        
        if action_type == "DONE":
            log("   └─ SUCCESS: LLM confirms application completed.")
            return True
            
        target_el = None
        for el in elements:
            if el["index"] == target_idx:
                target_el = el["handle"]
                break
                
        if not target_el:
            log("   └─ Error: Target element handle not found.")
            return False
            
        if action_type == "CLICK":
            success = await robust_click(target_el, page)
            if not success:
                return False
            await page.wait_for_timeout(3000)
            pages = context.pages
            if len(pages) > 1 and page != pages[-1]:
                page = pages[-1]
                await page.bring_to_front()
                
        elif action_type == "FILL":
            val = decision["fill_value"]
            success = await robust_fill(target_el, val)
            if not success:
                return False
            
        elif action_type == "UPLOAD":
            pdf_path = profile["resume_pdf_path"]
            if os.path.exists(pdf_path):
                await target_el.set_input_files(pdf_path)
                log(f"   └─ Uploaded local resume PDF.")
            else:
                log(f"   └─ Error: Resume not found at {pdf_path}")
                return False
                
    return False

# Main Autopilot Crawler
# Dynamic Login Gate for Internshala
async def wait_for_login(page):
    log("[Login Gate] Checking Internshala login status...")
    try:
        await page.goto("https://internshala.com/", timeout=60000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        log(f"[Login Gate] Navigation warning: {e}")
        
    url = page.url
    
    # Try to detect if already logged in quickly
    try:
        is_logged_in = "student/dashboard" in url or await page.query_selector(".profile_container, #profile-dropdown, .nav-profile, a[href*='/student/dashboard']")
        if is_logged_in:
            log("[Login Gate] SUCCESS: Authenticated session detected! Resuming...")
            return
    except Exception:
        pass
        
    log("=" * 60)
    log("[ACTION REQUIRED] Please log in to Internshala in the opened Chrome window.")
    log("If a login popup doesn't appear, click the 'Login' button at the top right.")
    log("The script will automatically detect when you are logged in and resume.")
    log("=" * 60)
    
    while True:
        try:
            url = page.url
            # Check for standard logged-in indicators
            logged_in_url = "student/dashboard" in url
            profile_icon = await page.query_selector(".profile_container, #profile-dropdown, .nav-profile, a[href*='/student/dashboard']")
            
            if logged_in_url or profile_icon:
                log("\n[Login Gate] SUCCESS: Authenticated session detected! Resuming...")
                break
        except Exception:
            pass
        await asyncio.sleep(2.0)

async def run_autopilot():
    os.makedirs("logs", exist_ok=True)
    with open("logs/autopilot.log", "w", encoding="utf-8") as f:
        f.write("=== EASYAPPLY AUTOPILOT RUN LOG ===\n")
        
    with open("profile.json", "r") as f:
        profile = json.load(f)
        
    log("=" * 60)
    log(f"Starting EasyApply Autopilot for: {profile['full_name']}")
    log("Goal Stream: Latest Jobs Feed (Option A)")
    log("Backend: Local Ollama (llama3.2:3b)")
    log("=" * 60)
    
    # Auto-Launch Chrome
    launch_chrome()
    if not is_chrome_running():
        await asyncio.sleep(3.0)
        

    async with async_playwright() as p:
        try:
            # Connect to local Chrome debugging session
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            
            if not context.pages:
                page = await context.new_page()
            else:
                page = context.pages[0]
                
            # 1. Trigger Interactive Login Gate
            await wait_for_login(page)
            
            processed_urls = set()
            applied_count = 0
            
            # Define high-relevance tech categories for Internshala
            categories = ["python", "software-development", "artificial-intelligence-ai", "machine-learning"]
            custom_kw = profile.get("target_keyword")
            if custom_kw:
                import re
                normalized_kw = re.sub(r'[^a-z0-9]+', '-', custom_kw.lower().strip()).strip('-')
                if normalized_kw and normalized_kw not in categories:
                    categories.insert(0, normalized_kw)
            
            for category in categories:
                log(f"\n[Scouting] Searching Internshala for category: '{category}'")
                
                # Autopilot page-by-page loop
                for page_num in range(1, 3):
                    search_url = f"https://internshala.com/jobs/{category}-jobs/page-{page_num}/"
                    log(f"[Scouting] Navigating to: {search_url}")
                    try:
                        await page.goto(search_url)
                        log("[Scouting] Waiting for job listings to load...")
                        await page.wait_for_selector(".individual_internship", timeout=8000)
                    except Exception:
                        log(f"Failed to load page {page_num} for category '{category}' or no jobs rendered. Skipping.")
                        continue
                    
                    # Extract cards on current page
                    raw_cards = await page.query_selector_all(".individual_internship")
                    cards_metadata = []
                    
                    for idx, card_el in enumerate(raw_cards):
                        try:
                            visible = await card_el.is_visible()
                            if not visible:
                                continue
                                
                            # Locate detail link
                            title_anchor = await card_el.query_selector("a[href*='/job/detail/'], a[href*='/internship/detail/']")
                            if not title_anchor:
                                continue
                                
                            href = await title_anchor.get_attribute("href")
                            if not href:
                                continue
                            if href.startswith("/"):
                                href = "https://internshala.com" + href
                                
                            if href in processed_urls:
                                continue
                                
                            summary = await card_el.inner_text()
                            summary = summary.strip().replace("\n", " ")
                            
                            title_text = await title_anchor.inner_text()
                            company_el = await card_el.query_selector("a.link_display_like_text, .company-name, .company_name")
                            company_text = await company_el.inner_text() if company_el else "Unknown"
                            
                            cards_metadata.append({
                                "index": idx,
                                "title": title_text.strip(),
                                "company": company_text.strip(),
                                "summary": summary[:400],
                                "url": href,
                                "handle": card_el
                            })
                        except Exception:
                            pass
                    
                    if not cards_metadata:
                        log(f"No job cards found on page {page_num}.")
                        continue
                        
                    log(f"Found {len(cards_metadata)} job cards on page {page_num}. Sending to local LLM for pre-screening...")
                    
                    # Call LLM to screen the cards in ONE single call
                    qualified_indices = await pre_screen_job_cards(cards_metadata, profile)
                    
                    # Filter qualified cards
                    qualified_cards = [card for card in cards_metadata if card["index"] in qualified_indices]
                    log(f"Pre-screener qualified {len(qualified_cards)} / {len(cards_metadata)} cards to visit.")
                    
                    # Loop through qualified listings only
                    for i, card in enumerate(qualified_cards):
                        link = card["url"]
                        processed_urls.add(link)
                        
                        log(f"\n--- [Screening Job: Page {page_num} | {i+1}/{len(qualified_cards)}] ---")
                        log(f"URL: {link}")
                        
                        try:
                            await page.goto(link)
                            await page.wait_for_timeout(3000)
                            
                            # Scrape details
                            title_el = await page.query_selector("span.profile_heading") or await page.query_selector("div.heading_container h1")
                            company_el = await page.query_selector("a.link_display_like_text") or await page.query_selector("div.heading_container a.company_name")
                            desc_el = await page.query_selector(".text-container") or await page.query_selector("#job_description")
                            salary_el = await page.query_selector(".salary_container") or await page.query_selector(".item_body:has-text('LPA')") or await page.query_selector(".item_body:has-text('Lakh')")
                            location_el = await page.query_selector("#location_names") or await page.query_selector(".location_link")
                            
                            title = await title_el.inner_text() if title_el else card["title"]
                            company = await company_el.inner_text() if company_el else card["company"]
                            description = await desc_el.inner_text() if desc_el else ""
                            salary = await salary_el.inner_text() if salary_el else "Not Specified"
                            location = await location_el.inner_text() if location_el else "Remote/Not Specified"
                            
                            title = title.strip()
                            company = company.strip()
                            salary = salary.strip().replace("\n", " ")
                            location = location.strip().replace("\n", " ")
                            
                            log(f"Scraped details -> Salary: {salary} | Location: {location}")
                            
                            # Verify final fit
                            match_result = await check_job_match(title, company, description[:1500], salary, location, profile)
                            
                            if match_result["match"]:
                                max_apps = profile.get("max_applications_per_run", 5)
                                if applied_count < max_apps:
                                    log(f"-> [ACTION: APPLYING] FIT CONFIRMED. Starting Apply Flow for: {title} @ {company}")
                                    success = await execute_application_flow(page, context, profile)
                                    if success:
                                        applied_count += 1
                                        tracker.log_application(
                                            platform="Internshala",
                                            company=company,
                                            job_title=title,
                                            job_url=link,
                                            location=location,
                                            salary_range=salary,
                                            status="Applied",
                                            resume_used=os.path.basename(profile.get("resume_pdf_path", "")),
                                            notes="Auto-applied via Internshala bot"
                                        )
                                        log(f"-> [TRACKING SUCCESS] Applied + logged: '{title}' at '{company}' on Internshala.")
                                else:
                                    log(f"-> [ACTION: SKIPPED (LIMIT REACHED)] FIT CONFIRMED for: {title} @ {company}. Max {max_apps} applications reached for this run.")
                            else:
                                log(f"-> [ACTION: SKIPPED (MISMATCH)] Not a match: {title} @ {company}")
                        except Exception as job_err:
                            log(f"Failed to process job listing: {job_err}")
                            
                    if applied_count >= profile.get("max_applications_per_run", 5):
                        break
                
                if applied_count >= profile.get("max_applications_per_run", 5):
                    break
            
            await browser.close()
            log("\n" + "=" * 60)
            log(f"Autopilot finished! Total jobs applied: {applied_count}")
            log("=" * 60)
            
        except Exception as e:
            log(f"Autopilot Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_autopilot())
