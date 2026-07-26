# MVP Specification & Engineering Blueprint: EasyApply India

This document serves as the ultimate handbook and technical specification for building the **EasyApply India** local-first desktop application. It outlines the core features, architecture, engineering constraints, unit economics, and marketing playbook.

---

## 1. Product Specification & Tier Model

### 1.1 Core Value Proposition
An autonomous job application agent running locally on the candidate's laptop. It crawls jobs, filters them using a smart LLM matcher to prevent spam applications, autofills forms, and logs applications to a visual Kanban tracking board.

### 1.2 The Freemium Pricing Model
To maximize user acquisition in the price-sensitive Indian market, we utilize a **Freemium model**:

| Feature / Limit | Free Tier | Premium Tier (₹699/month) |
| :--- | :--- | :--- |
| **Applications Cap** | 3 per day | **Unlimited** |
| **Execution Mode** | On-screen visible automation | **Background Autopilot (Minimized to system tray)** |
| **Supported Portals** | Internshala only | **Naukri, LinkedIn, Internshala, and Corporate Portals** |
| **AI Resume Customization**| ❌ No (sends standard static resume) | **🟢 Yes (AI customizes resume/cover letter keywords to pass ATS)** |
| **Analytics & History** | Basic log | **Full Kanban tracker board** |

---

## 2. Technical & System Architecture

The application is built using a **Local-First Architecture** to bypass bot blocks and eliminate hosting overhead.

```
+-------------------------------------------------------------------+
|                     User's Local Laptop                           |
|                                                                   |
|   +-----------------------+           +-----------------------+   |
|   |   Electron Shell      |           |  Python Engine        |   |
|   |   (React Frontend)    | <-------> |  (Playwright Core)    |   |
|   +-----------------------+    IPC    +-----------------------+   |
|               |                                   |               |
|               v                                   v               |
|   +-----------------------+           +-----------------------+   |
|   |  Local SQLite DB      |           | User's Local Chrome   |   |
|   |  (Profile & Cookies)  |           | (Active session)      |   |
|   +-----------------------+           +-----------------------+   |
+-------------------------------------------------------------------+
```

### 2.1 The Components
1. **Frontend Wrapper (Electron + React)**:
   - Provides the desktop dashboard UI.
   - Stores the candidate's profile, resume, and application history locally in a SQLite database.
   - Periodically queries the FastAPI license server to check subscription status.
2. **Automation Core (Python + Playwright)**:
   - Packaged as a local binary inside the installer.
   - Launches a Chromium instance using the candidate's local Chrome User Data Directory (`userDataDir`).
3. **Cloud License & Config Server (FastAPI + Supabase/DigitalOcean)**:
   - Validates license keys on app startup.
   - Serves the latest portal HTML selectors via JSON to prevent scraper breakage.

---

## 3. Core Engineering Rules & Hacks

When building the automation core, developers must follow these strict rules to avoid bot-bans and failures:

### Rule 1: Attaching to Local User Sessions
Never launch isolated headless browsers. The agent must launch Chromium with the user's active session.
- **Why**: Bypasses 2-Factor Authentication (2FA) and login redirects. If the user is already logged in to LinkedIn/Naukri on their laptop, the agent inherits the cookies and applies instantly.

### Rule 2: The CAPTCHA & OTP Hand-Off
When the Playwright script detects a CAPTCHA or an email OTP input box:
1. The script pauses execution.
2. The Electron app triggers a desktop alert: *"Action Required: Please solve the security verification on screen."*
3. The browser window slides to the front. The user completes the CAPTCHA manually in 5 seconds.
4. The user clicks "Resume" in the app, and the script continues automatically.

### Rule 3: Dynamic Selector Updates (Zero-Downtime Fixes)
To prevent the app from breaking when Naukri or LinkedIn changes their button IDs or HTML structure:
- **Never hardcode CSS selectors** in the local Python code.
- Always load them dynamically from your FastAPI backend on startup:
  ```python
  selectors = fetch_selector_map_from_server()
  page.click(selectors["naukri"]["apply_button"])
  ```

### Rule 4: Human Simulation Delays
Playwright actions must mimic human typing speed and click patterns:
- Implement a random delay (e.g. `1.5s - 3.5s`) between page navigations.
- Use `page.keyboard.type(text, delay=100)` to simulate real keypress typing rather than instant value setting.

---

## 4. Economic Feasibility & Profit Projections

* **Subscription Fee**: ₹699 / month (recurring).
* **AI API Cost**: ₹15 / user / month (average 100 applications using Llama-3.3-70B on Groq or GPT-4o-mini).
* **Server/Hosting Cost**: ₹2 / user / month.
* **Payment Gateway Fee (Razorpay)**: ₹14 / transaction (2%).
* **Total Cost Per User**: ~₹31 / month.
* **Net Profit Margin**: **95.5%** (approx. **₹668 profit** per user).

### Income Projections
* **100 Paying Users**: ₹69,900/mo revenue -> **₹66,800/mo net profit**.
* **1,000 Paying Users**: ₹6,99,000/mo revenue -> **₹6,68,000/mo net profit**.
* **5,000 Paying Users**: ₹34,95,000/mo revenue -> **₹33,40,000/mo net profit**.

---

## 5. Trust & Desktop Packaging (Critical Hurdles)

The largest friction point is user download trust.
1. **EV Code Signing Certificate**: You **must** purchase an EV Code Signing Certificate. Unsigned desktop apps trigger Microsoft SmartScreen warnings that scare users away. A signed installer executes seamlessly.
2. **App Size Optimization**: Minimize the installer size. Package Python and Chromium efficiently to keep the download under **150MB**.

---

## 6. Lean MVP Validation Playbook

Do not build the entire system first. Follow this validation path:

1. **Phase 1: Proof of Concept Script (Days 1-3)**:
   - Write a simple local Python script that connects to the user's active Chrome browser via debugging port (`--remote-debugging-port=9222`).
   - Program it to apply to 5 jobs on LinkedIn/Naukri.
2. **Phase 2: The Landing Page (Days 4-6)**:
   - Create a clean web landing page (`easyapply.in`).
   - Embed a 45-second screen recording showing the script automatically filling out Naukri forms.
   - Add a "Pre-order Premium for ₹299/mo (standard ₹699/mo)" call-to-action button.
3. **Phase 3: The Fake Door Test (Days 7-10)**:
   - When users click the buy button, show a waitlist sign-up: *"Slots full for this week. Enter your email to reserve your slot."*
   - If 30+ users register/click, demand is validated. We start packaging the Electron app.
