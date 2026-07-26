import asyncio
import json
import os
import re
import subprocess
import socket
import sys
import urllib.parse
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

# Global logger helper — writes to naukri.log for the orchestrator
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    formatted_msg = f"[{timestamp}] {message}"
    # Safe print: replace any unencodable chars instead of crashing
    print(formatted_msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)

    os.makedirs("logs", exist_ok=True)
    with open("logs/naukri.log", "a", encoding="utf-8", errors="replace") as f:
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

# Programmatic Python Salary Parser (Production-Level Regex)
def parse_salary_to_lpa(salary_str):
    if not salary_str:
        return None
    s = salary_str.lower().strip()
    if "not disclosed" in s or "not specified" in s or "not disclosed" in s:
        return None
        
    # Clean commas and extra whitespaces
    s = s.replace(",", "")
    
    # Find numbers (integers or decimals)
    numbers = re.findall(r"(\d+(?:\.\d+)?)", s)
    if not numbers:
        return None
        
    # Parse to floats
    parsed_nums = [float(n) for n in numbers]
    
    # Detect unit multiplier
    multiplier = 1.0 # default
    
    is_lakhs = "lac" in s or "lakh" in s or "lpa" in s or "l.p.a" in s
    is_crore = "cr" in s or "crore" in s
    
    if is_crore:
        multiplier = 100.0 # 1 Cr = 100 Lakhs
    elif is_lakhs:
        multiplier = 1.0
    else:
        # Check if the numbers are large raw numbers, e.g. 500000
        if any(n >= 1000 for n in parsed_nums):
            # Raw yearly salary, e.g., 500000 -> divide by 100,000 to get LPA
            return max(parsed_nums) / 100000.0
        else:
            # Small numbers, assume LPA by default
            multiplier = 1.0
            
    return max(parsed_nums) * multiplier

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

# Query Ollama to extrapolate search keywords from description dynamically
async def extrapolate_search_keywords(profile):
    job_description = profile.get("target_job_description", "")
    skills = profile.get("skills", [])
    
    prompt = f"""
You are the career path matching system for the EasyApply Autonomous Job Agent.
Analyze the candidate's target preferences and their listed skills.

Do NOT just extract literal words. Instead, brainstorm and generate a COMPREHENSIVE list of 8-10 distinct job roles/titles in today's tech market that this candidate is qualified and eligible to apply for based on their technology stack and target area. 

Candidate Target Preferences:
{job_description}

Candidate Skills:
{", ".join(skills)}

Rules for generating the comprehensive list of roles:
1. Include specific AI/LLM roles (e.g. 'AI Agent Developer', 'Generative AI Engineer', 'LLM Engineer').
2. Include core backend & API development roles matching their Python/FastAPI stack (e.g. 'Python Developer', 'Backend Developer', 'FastAPI Developer', 'API Developer').
3. Include general software engineering and cloud capability roles matching their Docker/AWS/GCP/CI-CD stack (e.g. 'Software Development Engineer', 'Software Engineer', 'Cloud Developer').
4. Keep the search terms standard, popular, and clean. Do not include experience level, salary, or location words.
5. Generate between 8 and 10 unique search terms.

Return your decision ONLY as a valid JSON object matching this structure:
{{
  "reasoning": "Explain which career paths and technology stack mappings you included to maximize their job search coverage",
  "keywords": ["market-role-1", "market-role-2", "market-role-3", "market-role-4", "market-role-5", "market-role-6", "market-role-7", "market-role-8", "market-role-9", "market-role-10"]
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        res = await robust_ollama_api_call(messages)
        log(f"[AI Keyword Generator] Extrapolated search keywords: {res['keywords']}")
        return res["keywords"]
    except Exception as e:
        log(f"[AI Keyword Generator Failed] Falling back to default keywords. Error: {e}")
    return ["python backend developer", "ai engineer", "fastapi developer", "software development engineer"]

# Helper to pre-screen a single batch of 10 cards dynamically
async def pre_screen_single_batch(batch_cards, profile):
    cards_text = ""
    for card in batch_cards:
        cards_text += f"Index: {card['index']} | Title: '{card['title']}' | Company: '{card['company']}' | Details: '{card['summary']}'\n"
        
    prompt = f"""
You are the pre-screening filter of the EasyApply Autonomous Job Agent.
Analyze the following list of job cards and decide which ones match the candidate's specific goals.
You must disqualify non-matching roles or roles with salary ranges explicitly lower than candidate expectations to save browser loading time.

Candidate Job Search Goals & Preferences:
{profile.get('target_job_description', '')}

Candidate Profile Details:
- Expected CTC: {profile['expected_ctc']} INR per year
- Experience: {profile['total_experience_years']}

Job Cards to evaluate:
{cards_text}

Decision Rules:
- Set match = true only for jobs that match the candidate's target job description.
- Set match = false for mismatching fields or roles that have salaries explicitly below candidate expectations.
- IMPORTANT: If the salary is "Not disclosed", "Not Specified", or empty, DO NOT mark it as false. Assume it is a match on salary and check for role fit.

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
    log(f"[AI Pre-Screener] Batching screening of {len(cards)} Naukri jobs into {len(batches)} groups using local Ollama...")
    
    for idx, batch in enumerate(batches):
        try:
            log(f"   └─ Screening batch {idx+1}/{len(batches)} (Cards {batch[0]['index']} to {batch[-1]['index']})...")
            batch_qualified = await pre_screen_single_batch(batch, profile)
            qualified_indices.extend(batch_qualified)
            await asyncio.sleep(1.0)
        except Exception as e:
            log(f"   └─ Batch {idx+1} screening failed: {e}")
            qualified_indices.append(batch[0]["index"])
            
    log(f"[AI Pre-Screener Completed] Selected Card Indices to visit: {qualified_indices}")
    return qualified_indices

# Query local Ollama to check if the job description matches preferences dynamically
async def check_job_match(title, company, description, salary, location, profile):
    # Programmatic Python-level Salary Filter Safeguard
    max_lpa = parse_salary_to_lpa(salary)
    if max_lpa is not None:
        if max_lpa < 10.0:
            log(f"-> [Python Filter Mismatch] Skipped job '{title}' because max salary ({max_lpa} LPA) is less than minimum 10.0 LPA expected.")
            return {"match": False, "reasoning": f"Programmatic check: max salary {max_lpa} LPA is below threshold."}
            
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
1. Reject (match = false) if the maximum Salary Range is explicitly less than the Candidate's Expected CTC (e.g. if expected is 10 LPA and salary range is 3-6 LPA, it is a mismatch).
2. IMPORTANT: If the salary is "Not disclosed", "Not Specified", or contains no numeric limits, DO NOT reject the job. Assume it is a match on salary and check for role fit.
3. Reject (match = false) if the job requires significantly more experience than the candidate has.
4. Set match = true only if the role field, technology/domain stack, salary range, and locations align with the candidate's specific preferences.

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
        screenshot_path = os.path.join(artifact_dir, f"naukri_step_{step}.png")
        try:
            await page.screenshot(path=screenshot_path)
        except Exception:
            pass
            
        # Scope to modal if visible (targeting common Naukri and general form selectors)
        modal_selectors = [".apply-modal", "div[role='dialog']", ".modal-dialog", ".form-container", "form", ".chatbot_Drawer", "[class*='drawer']", "[class*='chatbot']"]
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
            log(f"   └─ Detected open form/modal dialog. Scoping interactive elements inside it.")
            raw_elements = await active_modal.query_selector_all("input, textarea, select, button, a.apply, [contenteditable='true']")
        else:
            raw_elements = await page.query_selector_all("input, textarea, select, button, a.apply, [contenteditable='true']")
            
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
        
        target_el = None
        for el in elements:
            if el["index"] == target_idx:
                target_el = el["handle"]
                is_editable = el["editable"]
                tag_name = el["tag"]
                break
                
        if not target_el:
            log("   └─ Error: Target element handle not found.")
            return False
            
        # Code-level safeguard: Override FILL to CLICK on non-editable elements
        if action_type == "FILL" and not is_editable:
            log(f"   └─ [Safe Override] LLM tried to FILL non-editable element ({tag_name}). Overriding action to CLICK.")
            action_type = "CLICK"
            
        if action_type == "DONE":
            log("   └─ SUCCESS: LLM confirms application completed.")
            return True
            
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

# Dynamic Login Gate
async def wait_for_login(page):
    log("[Login Gate] Navigating to Naukri login page...")
    await page.goto("https://www.naukri.com/nlogin/login")
    
    log("=" * 60)
    log("[ACTION REQUIRED] Please complete login in the opened Chrome window.")
    log("The script will automatically detect when you are logged in and resume.")
    log("=" * 60)
    
    while True:
        try:
            url = page.url
            if "nlogin/login" not in url:
                nlogo = await page.query_selector("a.nLogo, .nSideBar, a[href*='/mnj/']")
                logged_in_url = "mnj" in url or "homepage" in url or "dashboard" in url
                
                if nlogo or logged_in_url:
                    log("\n[Login Gate] SUCCESS: Authenticated session detected! Resuming...")
                    break
        except Exception:
            pass
        await asyncio.sleep(2.0)

# Main Autopilot Crawler for Naukri.com
async def run_naukri_autopilot():
    os.makedirs("logs", exist_ok=True)
    with open("logs/autopilot.log", "w", encoding="utf-8") as f:
        f.write("=== NAUKRI EASYAPPLY AUTOPILOT RUN LOG ===\n")
        
    with open("profile.json", "r") as f:
        profile = json.load(f)
        
    log("=" * 60)
    log(f"Starting Naukri Autopilot for: {profile['full_name']}")
    log("Backend: Local Ollama (llama3.2:3b)")
    log("=" * 60)
    
    # Auto-Launch Chrome
    launch_chrome()
    if not is_chrome_running():
        await asyncio.sleep(3.0)
        
    # Extrapolate keywords dynamically using Llama 3.2 3B
    keywords = await extrapolate_search_keywords(profile)
    
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
            
            # Loop through extrapolated keywords
            for keyword in keywords:
                log(f"\n[Scouting] Searching Naukri for keyword: '{keyword}'")
                encoded_keyword = urllib.parse.quote(keyword)
                
                # Scan first 2 pages of search results for this keyword
                for page_num in range(1, 3):
                    search_url = f"https://www.naukri.com/jobs-in-india-{page_num}?k={encoded_keyword}"
                    log(f"[Scouting] Navigating to: {search_url}")
                    
                    try:
                        await page.goto(search_url)
                        log("[Scouting] Waiting for search results to load...")
                        await page.wait_for_selector("div.srp-jobtuple-wrapper, article.jobTuple", timeout=8000)
                    except Exception:
                        log(f"Failed to load or find job tuples for keyword '{keyword}' page {page_num}. Skipping.")
                        continue
                    
                    # Extract job card element metadata
                    raw_cards = await page.query_selector_all("div.srp-jobtuple-wrapper, article.jobTuple")
                    cards_metadata = []
                    
                    for idx, card_el in enumerate(raw_cards):
                        try:
                            title_anchor = await card_el.query_selector("a.title, a.job-tuple-title")
                            if not title_anchor:
                                continue
                                
                            href = await title_anchor.get_attribute("href")
                            if not href:
                                continue
                            if href.startswith("/"):
                                href = "https://www.naukri.com" + href
                                
                            if href in processed_urls:
                                continue
                                
                            title_text = await title_anchor.inner_text()
                            company_el = await card_el.query_selector("a.comp-name-link, .comp-name, .company-info, .companyName")
                            company_text = await company_el.inner_text() if company_el else "Unknown"
                            
                            summary_el = await card_el.query_selector("span.job-desc, .jobDescription, .job-desc")
                            summary_text = await summary_el.inner_text() if summary_el else ""
                            
                            # Card-Level Experience, Salary, and Location wildcards
                            exp_el = await card_el.query_selector("span.expwdBorder, span.experience, .exp, [class*='experience']")
                            exp_text = await exp_el.inner_text() if exp_el else "Not Specified"
                            
                            sal_el = await card_el.query_selector("span.sal, span.salary, .salary, [class*='salary']")
                            sal_text = await sal_el.inner_text() if sal_el else "Not Specified"
                            
                            loc_el = await card_el.query_selector("span.loc, span.location, .loc, [class*='location']")
                            loc_text = await loc_el.inner_text() if loc_el else "Not Specified"
                            
                            cards_metadata.append({
                                "index": idx,
                                "title": title_text.strip(),
                                "company": company_text.strip(),
                                "summary": summary_text.strip()[:400],
                                "url": href,
                                "experience": exp_text.strip(),
                                "salary": sal_text.strip(),
                                "location": loc_text.strip(),
                                "handle": card_el
                            })
                        except Exception:
                            pass
                            
                    if not cards_metadata:
                        log("No job cards found on this page.")
                        continue
                        
                    log(f"Found {len(cards_metadata)} job cards. Sending to local LLM for pre-screening...")
                    qualified_indices = await pre_screen_job_cards(cards_metadata, profile)
                    
                    qualified_cards = [card for card in cards_metadata if card["index"] in qualified_indices]
                    log(f"Pre-screener qualified {len(qualified_cards)} / {len(cards_metadata)} cards to visit.")
                    
                    # Process qualified detailed listings
                    for i, card in enumerate(qualified_cards):
                        link = card["url"]
                        processed_urls.add(link)
                        
                        log(f"\n--- [Screening Naukri Job | {i+1}/{len(qualified_cards)}] ---")
                        log(f"URL: {link}")
                        
                        try:
                            await page.goto(link)
                            await page.wait_for_timeout(3000)

                            # Scrape detailed description page info
                            title_el = await page.query_selector("h1.jd-header-title, span.profile_heading")
                            company_el = await page.query_selector("div.jd-header-comp-name a, a.comp-name-link")
                            desc_el = await page.query_selector("section.job-desc, .job-desc, #jobDescription")
                            salary_el = await page.query_selector("div.salary span, .sal, span.sal")
                            location_el = await page.query_selector("div.location span, .location, span.loc")
                            
                            title = await title_el.inner_text() if title_el else card["title"]
                            company = await company_el.inner_text() if company_el else card["company"]
                            description = await desc_el.inner_text() if desc_el else ""
                            
                            # Resilient Selector Fallbacks: Use card details if detail page returns empty/Not Specified
                            salary = await salary_el.inner_text() if salary_el else ""
                            salary = salary.strip().replace("\n", " ")
                            if not salary or "not disclosed" in salary.lower() or "not specified" in salary.lower():
                                salary = card["salary"]
                                
                            location = await location_el.inner_text() if location_el else ""
                            location = location.strip().replace("\n", " ")
                            if not location or "not specified" in location.lower():
                                location = card["location"]
                            
                            title = title.strip()
                            company = company.strip()
                            
                            log(f"Scraped details -> Salary: {salary} | Location: {location}")
                            
                            # Verify final fit dynamically using local LLM
                            match_result = await check_job_match(title, company, description[:1500], salary, location, profile)
                            
                            if match_result["match"]:
                                # Locate the Apply button (checks buttons, links, spans, divs containing Apply or Interested)
                                apply_btn = await page.query_selector(
                                    "//button[contains(text(), 'Apply') or contains(text(), 'Interested') or contains(text(), 'Apply on company site')] | "
                                    "//a[contains(text(), 'Apply') or contains(text(), 'Interested') or contains(text(), 'Apply on company site')] | "
                                    "//span[contains(text(), 'Apply') or contains(text(), 'Interested')] | "
                                    "//div[contains(text(), 'Apply') or contains(text(), 'Interested')]"
                                )
                                
                                if not apply_btn:
                                    log("   └─ Error: Apply button not found on detail page.")
                                    continue
                                    
                                btn_text = (await apply_btn.inner_text()).lower()
                                is_external = "company site" in btn_text
                                
                                if applied_count < profile.get("max_applications_per_run", 5):
                                    if is_external:
                                        log(f"-> [ACTION: EXTERNAL APPLY MATCHED] FIT CONFIRMED. Saving external apply link for manual review: {title} @ {company}")
                                        tracker.log_application(
                                            platform="Naukri",
                                            company=company,
                                            job_title=title,
                                            job_url=link,
                                            location=location,
                                            salary_range=salary,
                                            status="Manual Apply Needed",
                                            resume_used=os.path.basename(profile.get("resume_pdf_path", "")),
                                            notes="Requires redirecting to company site. URL saved for manual application."
                                        )
                                        log(f"-> [TRACKING SAVED] External apply link logged for manual review.")
                                    else:
                                        # Internal apply
                                        log(f"-> [ACTION: APPLYING INTERNAL] FIT CONFIRMED. Starting Apply Flow for: {title} @ {company}")
                                        
                                        # Capture pages before click to detect redirects
                                        success = await robust_click(apply_btn, page)
                                        if success:
                                            await page.wait_for_timeout(3000)
                                            
                                            # Check if redirected to external site
                                            pages = context.pages
                                            redirected = False
                                            external_url = ""
                                            
                                            if len(pages) > 1:
                                                # New tab opened (external link)
                                                new_page = pages[-1]
                                                external_url = new_page.url
                                                if "naukri.com" not in external_url:
                                                     redirected = True
                                                     await new_page.close()
                                            elif "naukri.com" not in page.url:
                                                 # Current page navigated away
                                                 redirected = True
                                                 external_url = page.url
                                                 try:
                                                     await page.go_back()
                                                     await page.wait_for_timeout(2000)
                                                 except Exception:
                                                     pass
                                                     
                                            if redirected:
                                                log(f"   └─ Redirected to external site: {external_url}. Saving link to tracker for manual review.")
                                                tracker.log_application(
                                                    platform="Naukri",
                                                    company=company,
                                                    job_title=title,
                                                    job_url=link,
                                                    location=location,
                                                    salary_range=salary,
                                                    status="Manual Apply Needed",
                                                    resume_used=os.path.basename(profile.get("resume_pdf_path", "")),
                                                    notes=f"Redirected to external application: {external_url}"
                                                )
                                                log(f"-> [TRACKING SAVED] External apply link logged for manual review: '{title}' at '{company}'.")
                                                continue
                                                
                                            # If not redirected, proceed with internal form filling
                                            form_success = await execute_application_flow(page, context, profile)
                                            if form_success:
                                                applied_count += 1
                                                tracker.log_application(
                                                    platform="Naukri",
                                                    company=company,
                                                    job_title=title,
                                                    job_url=link,
                                                    location=location,
                                                    salary_range=salary,
                                                    status="Applied",
                                                    resume_used=os.path.basename(profile.get("resume_pdf_path", "")),
                                                    notes="Auto-applied via Naukri (internal EasyApply)"
                                                )
                                                log(f"-> [TRACKING SUCCESS] Applied + logged: '{title}' at '{company}' on Naukri.")
                                else:
                                    apply_type = "EXTERNAL" if is_external else "INTERNAL"
                                    log(f"-> [ACTION: SKIPPED (LIMIT REACHED)] FIT CONFIRMED ({apply_type}) for: {title} @ {company}. Max {profile.get('max_applications_per_run', 5)} applications reached.")
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
            log(f"Naukri Autopilot finished! Total jobs applied: {applied_count}")
            log("=" * 60)
            
        except Exception as e:
            log(f"Autopilot Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_naukri_autopilot())
