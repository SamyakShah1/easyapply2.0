# EasyApply Technical Architecture Design

This document provides a simple, clear, and practical overview of the **EasyApply** system design.

---

## 1. System Components & Data Flow

```
                     ┌──────────────────────────────────────────────────┐
                     │              USER'S LOCAL LAPTOP                 │
                     │                                                  │
                     │   ┌──────────────────────────────────────────┐   │
                     │   │   Electron App UI (React Dashboard)      │   │
                     │   │   - Let's user edit profile details      │   │
                     │   │   - Displays Kanban application log      │   │
                     │   └────┬────────────────────────────────┬────┘   │
                     │        │ Writes to                      │ Reads  │
                     │        v                                v        │
                     │   ┌──────────────┐              ┌────────────┐   │
                     │   │ profile.json │              │ SQLite DB  │   │
                     │   │ (Notice, CTC)│              │ (Logs)     │   │
                     │   └────────┬─────┘              └────────────┘   │
                     │            │ Reads details                       │
                     │            v                                     │
                     │   ┌──────────────────────────────────────────┐   │
                     │   │   Python Engine (Playwright Core)        │   │
                     │   │   - Runs state machine loop              │   │
                     │   │   - Saves screenshots to logs/ folder    │   │
                     │   └────┬────────────────────────────────┬────┘   │
                     │        │ Connects (Port 9222)           │        │
                     │        v                                │        │
                     │   ┌────────────────────────────────┐    │        │
                     │   │   Active Chrome Browser        │    │        │
                     │   │   (User's IP & cookies)        │    │        │
                     │   └────────────────────────────────┘    │        │
                     └─────────────────────────────────────────┼────────┘
                                                               │ Queries (For custom text QA)
                                                               v
                                                      ┌──────────────────┐
                                                      │  Groq Cloud API  │
                                                      │  (Llama 3.3)     │
                                                      └──────────────────┘
```

---

## 2. Component Responsibility Directory

### 2.1 The Profile Database (`profile.json` & SQLite)
* **Location**: Local hard drive only.
* **Goal**: Keeps credentials, preferences, and logs 100% private.
* **Content**: Name, phone, experience, CTC, notice period, and local path to the resume PDF.

### 2.2 The Chrome Browser (Debugging Port 9222)
* **Location**: Local machine.
* **Goal**: Playwright hooks into this browser window via Chrome DevTools Protocol (CDP).
* **Benefit**: It uses the user's active login sessions and residential IP address, preventing the target portals (Naukri, LinkedIn, Internshala) from blocking the bot.

### 2.3 The Python Autopilot Engine (`local_poc.py`)
* **Location**: Standalone binary packaged with the app.
* **Goal**: Executes the core state machine run loop:
  1. Captures a screenshot to `logs/` for local diagnostic history.
  2. Identifies the current screen (e.g. details page, resume intermediate page, or form page).
  3. Clicks button or fills form inputs using the details inside `profile.json`.
  4. If a custom question is found, calls **Groq (Llama 3.3)** to write the answer.
  5. Submits application and logs success.

### 2.4 The Licensing Server (FastAPI Backend)
* **Location**: Cloud server.
* **Goal**: Verifies license keys on startup and serves the latest button CSS selectors dynamically.
