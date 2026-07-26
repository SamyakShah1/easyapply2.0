# Startup Game Plan: Launching EasyApply India

This document details the phased tactical roadmap for building, validating, monetizing, and scaling the **EasyApply** local-first desktop application for the Indian tech job market.

---

## Phase 1: Proof of Concept (PoC) Engine (Days 1–3)
**Goal**: Build a bare-minimum automation script to prove we can autofill forms locally on a user's machine without Cloudflare blocks.

* **Tasks**:
  1. Write a local Python script that connects to Chrome via debugging mode (`chrome.exe --remote-debugging-port=9222`).
  2. Implement Playwright handlers to automate **LinkedIn Quick Apply** and **Naukri** using the active Chrome profile session.
  3. Validate that the script successfully uploads a local resume PDF and fills common inputs (notice period, CTC, experience).
* **Exit Metric**: A successful test run applying to 5 real jobs on your machine under 1 minute.

---

## Phase 2: Landing Page & Fake Door Validation (Days 4–7)
**Goal**: Validate payment intent from real job seekers before writing any desktop app wrappers or backend systems.

* **Tasks**:
  1. **Record the Demo**: Capture a 45-second screen recording showing the Python script autofilling Naukri/LinkedIn applications at high speed.
  2. **Build the Landing Page**: Set up `easyapply.in` using React/Vite. The page must display the demo video prominently, outline the ₹699/month pricing, and showcase the Freemium model.
  3. **The Fake Door Test**: Add a "Start Free Trial" and "Buy Premium for ₹699" button. When clicked, it displays a popup: *"Slots full for this week. Enter your email to join the queue."*
* **Exit Metric**: **100+ email signups** or **30+ Premium button clicks** within 7 days.

---

## Phase 3: Desktop Shell & Core App Development (Days 8–20)
**Goal**: Package the script into a downloadable desktop application with a clean visual UI.

* **Tasks**:
  1. **Build the Electron/React UI**: Develop the onboarding wizard (profile fields, local resume upload) and the Kanban tracking dashboard.
  2. **Integrate Local Storage**: Use a local SQLite database to store user profile details and cookie sessions.
  3. **App Packaging**: Bundle the Python runtime, Playwright, and Chromium into a single executable (`.exe` for Windows, `.dmg` for Mac) using PyInstaller and Electron Builder.
* **Exit Metric**: A working local installer file under 150MB that installs, runs, and automates Internshala.

---

## Phase 4: License Server & Payments Integration (Days 21–27)
**Goal**: Build the commercial infrastructure to charge users and protect your software.

* **Tasks**:
  1. **FastAPI backend**: Build a lightweight central API server to generate and validate subscription licenses.
  2. **Razorpay & Stripe Integration**: Integrate Razorpay (essential for UPI/Indian debit cards) and Stripe for monthly recurring subscription billing.
  3. **Code Signing Certificate**: Purchase and apply an EV Code Signing Certificate to sign the installer binaries, preventing Microsoft SmartScreen warnings from blocking installations.
* **Exit Metric**: A user can pay ₹699 on our website, receive a License Key, paste it into the app, and unlock Premium features.

---

## Phase 5: Organic Launch & Distribution (Days 28–35)
**Goal**: Drive mass traffic to the landing page and acquire the first 100 paying customers for ₹0 marketing spend.

* **Tasks**:
  1. **Reddit Campaign**: Show-and-tell post on `r/developersIndia` showing the video and asking for beta testers.
  2. **LinkedIn Campaign**: Write a viral post outlining the struggle of applying manually and linking the tool.
  3. **Telegram/WhatsApp Outreach**: Distribute the video in placement preparation and job alert groups.
* **Exit Metric**: **50+ paying users** (₹35,000+ MRR).

---

## Phase 6: Scaling & Retention (Day 36+)
**Goal**: Retain users, automate more portals, and scale profit margins.

* **Tasks**:
  1. **Dynamic Selector Updates**: Set up the dynamic selector system where the app pulls HTML field mapping from our database on startup, preventing the app from breaking when job boards update their code.
  2. **AI CV Tailoring**: Implement the GPT-4o-mini / Llama-3.3 engine that scans the job description, rewrites resume bullet points, and generates customized PDF resumes locally for each application.
  3. **Affiliate Program**: Offer users 1 free month of premium for every friend they refer, creating a viral growth loop.
