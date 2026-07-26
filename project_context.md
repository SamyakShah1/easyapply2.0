# EasyApply India: Project Context & Handover Document

This document preserves the complete context, architectural decisions, and next steps for the AI engineering assistant to pick up development immediately in the next session.

---

## 1. Project Overview & Target
- **Product Name**: EasyApply India
- **Mission**: An autonomous local job application agent (desktop application) that crawls, screens, autofills, and submits applications on behalf of Indian job seekers.
- **Commercial Model**: ₹699/month subscription (97% profit margin).
- **Validation Model**: Freemium (3 applies/day free) -> triggers paywall for unlimited applies, AI resume tailoring, and Naukri/LinkedIn support.

---

## 2. Architectural Decisions (Local-First)
1. **Zero Server Overhead**: Playwright runs locally on the user's laptop using their residential IP. This completely bypasses Cloudflare/Akamai bot detection blocks that affect datacenter-hosted bots.
2. **Local Session Reuse**: The Playwright agent connects to the user's existing Chrome profile (`userDataDir`). This inherits active logins for LinkedIn, Naukri, and Internshala, removing the need for us to collect or store user passwords.
3. **Privacy Lock**: PDF resumes, passwords, and profile metadata are stored *only* inside a local SQLite database in the user's system app directory.
4. **Server Role**: The central FastAPI/Supabase server ONLY handles license validation, billing checks, and hosting the dynamic JSON selector map (to update broken selectors instantly without software updates).

---

## 3. Next Steps: Phase 1 Proof of Concept (PoC) Script
When resuming tomorrow, start by writing a local Python script `local_poc.py` to prove the local attachment and autofilling works:

### Step 1: Launch Local Chrome in Debugging Mode
We must instruct the user to close all Chrome instances and launch Chrome from the terminal with remote debugging enabled:
```bash
# Windows Chrome launch command
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-dev-profile"
```

### Step 2: Write the `local_poc.py` Script
The script attaches to the running Chrome instance using Chrome DevTools Protocol (CDP):
```python
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # Attach to the already running local Chrome instance
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0]
        
        # Test navigating and autofilling fields on a target page
        print(f"Attached to page: {await page.title()}")
        # ... logic to scan inputs and fill name/email/resume path ...
        
        await browser.close()

asyncio.run(run())
```

### Step 3: Record Demo Video
Record a 45-second screen capture of the script autofilling fields on LinkedIn Quick Apply or Internshala. This video will be used for the Phase 2 Landing Page validation.
