# Future Integration Plan: Modular ATS & Enterprise Portals

This document outlines the architectural blueprint for scaling the **EasyApply** automation engine to support direct applications on major ATS platforms (Greenhouse, Lever, Workday) and custom enterprise career portals (Google, Microsoft, Amazon) using a single, unified agent.

---

## 1. Core Architecture: The Modular Driver Registry

Instead of managing separate scripts for different platforms, the application uses a **Plugin-based Driver Architecture**. 

*   **Unified Agent Core**: Handles profile state (`profile.json`), database persistence (`applications.db`), LLM matching, browser setup (CDP port 9222), and dashboard UI.
*   **Modular Drivers**: Small, specialized scripts located in a dedicated `drivers/` directory that define selector structures and traversal rules for specific sites.

```
                         ┌──────────────────────────────────────────────┐
                         │              Core Autopilot Agent            │
                         └──────────────────────┬───────────────────────┘
                                                │ Routes by Domain
                                                v
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    v                           v                           v
         [drivers/google.py]           [drivers/lever.py]          [drivers/generic_llm.py]
         Custom Angular portal        Standard static form        Fallback LLM screen-filler
```

### 1.1 Driver Mapping Types

To scale coverage efficiently, drivers are categorized into two types:

1.  **Shared Platform Drivers (One-to-Many)**: 
    Many companies do not write their own job application software. Instead, they host their portals on standard platforms. A single driver file covers **thousands** of companies instantly.
    *   `drivers/lever.py`: Automates Figma, Vercel, Retool, Canva, and 10,000+ other companies using Lever.
    *   `drivers/greenhouse.py`: Automates Stripe, Airbnb, Uber, and 10,000+ other companies using Greenhouse.
    *   `drivers/workday.py`: Automates 1,000+ enterprise sites using Workday.
2.  **Proprietary Portal Drivers (One-to-One)**: 
    For tech giants that build custom systems from scratch, we write a dedicated company driver.
    *   `drivers/google.py`: Custom-designed for `careers.google.com`.
    *   `drivers/microsoft.py`: Custom-designed for `careers.microsoft.com`.
    *   `drivers/amazon.py`: Custom-designed for `amazon.jobs`.

### 1.2 Folder Layout Structure

The python automation engine incorporates these drivers under a clean, unified package:

```
autoapply/
│
├── drivers/
│   ├── __init__.py
│   ├── lever.py         # Covers 10,000+ Lever-hosted portals
│   ├── greenhouse.py    # Covers 10,000+ Greenhouse-hosted portals
│   ├── workday.py       # Covers 1,000+ Workday-hosted portals
│   ├── google.py        # Dedicated driver for Google Careers
│   ├── microsoft.py     # Dedicated driver for Microsoft Careers
│   ├── amazon.py        # Dedicated driver for Amazon Jobs
│   └── generic_llm.py   # General fallback screen-reading loop
│
├── profile.json
├── naukri_agent.py
└── autopilot_agent.py
```

---

## 2. Authentication Strategy: Session Inheriting (User-in-the-Loop)

*   **Rule**: The agent **never** handles passwords or authenticates automatically. Google and Microsoft instantly block automated browser logins.
*   **Solution**: The user logs in to their Google, Microsoft, or LinkedIn accounts **once manually** in the debugging Chrome browser. 
*   **CDP Session Reuse**: The agent attaches to the browser DevTools Protocol (port `9222`) and inherits active cookies, loading career pages pre-authenticated as the user.

---

## 3. Platform Integration Blueprint

### 3.1 Type A: Standard ATS Drivers (Lever, Greenhouse, Workday)
These handle the software suites that run 80%+ of mid-to-large tech company career pages.

| ATS Platform | Selector Strategy | Automation Logic |
| :--- | :--- | :--- |
| **Lever** | Static HTML attributes (e.g. `name="name"`, `name="email"`) | Single-page programmatic fill; instant file upload for resume; 99% success rate. |
| **Greenhouse** | Accessibility and standard selectors (`#first_name`, `#email`) | Single-page fill; locates custom questions and passes them to the local LLM. |
| **Workday** | Multi-page wizard panels (`[data-automation-id="..."]`) | Creates a portal account using credentials from `profile.json`, traverses multi-step panels, and submits. |

### 3.2 Type B: Proprietary Enterprise Portals (Google, Microsoft, Amazon)
These portals are custom-built, React/Angular single-page apps (SPAs) with heavy dynamic loading.

*   **Google Careers (`careers.google.com`)**:
    *   *Resume parsing first*: Uploads resume to let Google's parser fill contact info.
    *   *Dynamic Step Traverse*: Navigates the stepper wizard using stable Angular accessibility labels (e.g., `input[aria-label="First name"]`).
    *   *Disclosures mapping*: Automates visa sponsorship checks (`requires_visa_sponsorship`).
*   **Microsoft Careers (`careers.microsoft.com`)**:
    *   *LinkedIn SSO login*: Clicks "Apply with LinkedIn" to pull profile details instantly.
    *   *Custom radio selections*: Maps complex company questions (e.g., *"Former employee"* or *"Internal referrals"*) to static answers in the profile.

### 3.3 Type C: Generic LLM Fallback (Custom Sites)
*   For unmapped startup portals, the agent runs the **Generic LLM Flow** (screen-reading inputs and filling on the fly).
*   **Safety Switch**: If a page attempts a complex external redirect or requires manual auth, the agent cancels automation, logs the URL in the SQLite database under **`Manual Apply Needed`**, and proceeds to the next job.

---

## 4. Technical Safeguards

1.  **Shadow DOM Penetration**: Google and Microsoft use custom web components. The drivers must use Playwright locators (`page.locator()`) which natively penetrate Shadow DOM boundaries.
2.  **State Animation Locks**: Modern SPAs use slide/fade transitions. Drivers must wait for transitions to finish using state wait commands:
    ```python
    await page.wait_for_selector("button:has-text('Next'):not([disabled])")
    ```
3.  **Zero-Downtime Dynamic Selectors**: To prevent the app breaking during portal updates, the `drivers/` configuration and selector maps are updated on our central configuration server and pulled by the local app on startup.
