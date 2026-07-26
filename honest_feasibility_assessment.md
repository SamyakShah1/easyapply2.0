# Business & Technical Feasibility Report: EasyApply Local-First Desktop Agent

---

## 1. Executive Summary

This report evaluates the technical viability, economic feasibility, and market potential of building **EasyApply India**, an autonomous desktop job application agent. 

The core value proposition is to automate the job application pipeline (scraping, filtering via LLM, autofilling, and submitting) for Indian job seekers. By deploying a **local-first desktop architecture** (running on the user's laptop using their own IP and login sessions) rather than a cloud-hosted scraper, we bypass anti-bot systems (Cloudflare, Akamai) natively and eliminate hosting/proxy overhead. This cost reduction allows us to price the service disruptively at **₹699/month** with a **97% net profit margin**.

---

## 2. Technical Feasibility Analysis

Running browser automation bots inside datacenter environments (AWS, DigitalOcean, GCP) to apply to jobs is a solved technical problem but a failed commercial approach due to anti-bot detection. A local-first client approach changes the parameters.

### 2.1 The Bot Detection Problem & Solution
- **The Barrier**: Naukri, LinkedIn, and corporate portals employ strict Cloudflare and Akamai firewalls. Datacenter IP ranges are instantly blocked, and headless browser headers are easily flagged.
- **The Solution**: The desktop application runs on the user's own machine. It utilizes their local residential ISP connection, making the IP traffic look like standard consumer web usage.
- **Session Reuse**: The app leverages active browser sessions. By pointing the local Playwright driver to launch or attach to Chrome using the user's local Chrome User Data Directory (`userDataDir`), it inherits active login states (Naukri, LinkedIn, etc.) directly. The user does not need to store their passwords on a server.

### 2.2 Core Technical Challenge: Selector Drift
Job portals update their HTML layouts frequently. If a developer at Naukri changes a form button selector, the automation script fails.
- **Solution (Dynamic Selector Maps)**:
  - We build a server-driven selector API in our FastAPI backend.
  - On startup, the desktop app downloads a JSON dictionary of target selectors:
    ```json
    {
      "naukri": {
        "apply_button": "button.njob-apply",
        "resume_upload": "input[type='file']"
      }
    }
    ```
  - When selectors change, we edit the JSON on our server. The desktop clients update their mapping instantly without requiring a full application reinstall.

### 2.3 Desktop Client Tech Stack
- **Frontend/Shell**: **Electron** or **Tauri** (React/TypeScript). Electron provides a modern, premium UI and handles the desktop OS window wrappers.
- **Automation Core**: **Python + Playwright**. Python is packaged using PyInstaller and runs as a local background process spawned by Electron. Communication is handled via local IPC (Inter-Process Communication) or WebSockets.

---

## 3. Market Feasibility Analysis

### 3.1 Target Customer Profile (India)
The target audience consists of:
1. **Unemployed Grads & Junior Developers**: Willing to spend ₹699/month to increase their daily outreach and land their first job.
2. **Mid-level Career Switchers**: Desperate to leave their current service companies (TCS, Infosys, Wipro) but too busy with client work to spend 3 hours daily filling out application forms manually.

### 3.2 The Trust and Safety Barrier (Critical Risk)
- **Windows SmartScreen / Mac Gatekeeper**: Unsigned `.exe` and `.dmg` installers trigger scary red warnings when downloaded.
- **Mitigation**: We must purchase an **EV Code Signing Certificate** (approx. $300 - $400/year). Digitally signing the binary guarantees instant trust and bypasses Windows/Mac warnings, preventing a 90% drop in download conversions.

---

## 4. Economic Feasibility & Unit Economics

By shifting the heavy Playwright compute (rendering pages, running Chromium) to the client's CPU, the unit economics are highly profitable.

### 4.1 Cost Breakdown per User/Month
1. **Hosting/Compute**: **₹0** (runs on user's laptop).
2. **Proxies**: **₹0** (uses user's home internet).
3. **AI LLM Processing (Fast API calls for JD keyword extraction/CV tailoring)**:
   - Assuming 100 applications/month per user.
   - LLM: `llama-3.3-70b-versatile` via Groq Cloud API (cost: $0.59 per million input tokens).
   - Average tokens per application = 2,500 ($0.0014 USD).
   - Total LLM cost per user/month: **$0.14 USD (~₹12 INR)**.
4. **License Server/DB (Supabase / DigitalOcean)**: **~₹2 INR**.

* **Total Variable Cost**: **~₹14 INR**
* **Gross Pricing**: **₹699 INR**
* **Net Margin**: **~97.9%** (approx. **₹685 profit** per subscriber/month).

### 4.2 Financial Projections (Monthly Recurring Revenue)

| Active Subscribers | Monthly Revenue | Variable Cost (AI + DB) | Monthly Net Profit |
| :--- | :--- | :--- | :--- |
| **100** | ₹69,900 | ₹1,400 | **₹68,500** |
| **500** | ₹3,49,500 | ₹7,000 | **₹3,42,500** |
| **1,000** | ₹6,99,000 | ₹14,000 | **₹6,85,000** (~6.8L/mo) |
| **5,000** | ₹34,95,000 | ₹70,000 | **₹34,25,000** (~34.2L/mo) |

---

## 5. Lean MVP Validation Strategy (Our Next Steps)

Before coding the desktop packaging or setting up payment gateways, we must validate demand with zero waste.

```
[Build Local Python Script] ──> [Record Demo Video] ──> [Launch Landing Page] ──> [Pre-Orders (₹299/mo)]
```

### Action Plan:
1. **The Core Script**: Write a python script that connects to the user's running Chrome browser via debugging port (`--remote-debugging-port=9222`) and automates applying to 5 jobs on LinkedIn/Naukri.
2. **The Video**: Record a 45-second screen capture of the script in action.
3. **The Validation Landing Page**: Build a landing page showing the video with a waitlist checkout: *"Pre-order now for ₹299/mo (standard ₹699/mo) - Limited to first 100 users."*
4. **Success Metric**: If we get 30+ pre-orders within 1 week of launching the landing page, we proceed to package the Electron application.
