# Screen-by-Screen User Journey - EasyApply Desktop App

Here is the complete visual and interactive walkthrough of how a user experiences your product from purchase to getting interviews:

---

## Step 1: The Landing Page (`easyapply.in`)
1. **The Headline**: The user sees: *"An Autonomous Job Application Agent that applies for you on autopilot. Works locally on your machine."*
2. **Visual Proof**: An embedded high-speed video shows the app's browser automatically navigating to Naukri, filling out the forms, and uploading the resume in 3 seconds.
3. **Purchase**: The user buys the **₹699/month** subscription via Razorpay.
4. **Download**: The user instantly receives an email with their **License Key** and a download link for `EasyApply-Setup.exe` (Windows) or `EasyApply.dmg` (Mac).

---

## Step 2: Installation & Activation (First Run)
1. The user installs and launches the desktop app.
2. A sleek dark-mode window opens with a single input field:
   - **`[ Paste your License Key here ]`**
3. They paste the key and click **"Activate"**. The app verifies it against your FastAPI server and unlocks.

---

## Step 3: Profile Setup (Done Once)
The app displays a clean multi-step onboarding wizard to build their local profile:
* **Tab 1: Profile Details**: Name, Phone, Location, LinkedIn URL, GitHub URL.
* **Tab 2: Career Preferences**: Target Titles (e.g. *Frontend Developer*), Current CTC, Expected CTC, Notice Period.
* **Tab 3: Resume**: A drag-and-drop zone to upload their `resume.pdf`.
* **Tab 4: Cover Letter**: A template field with placeholders like `{{company_name}}` and `{{role_title}}`.

---

## Step 4: Connecting Portals (Saved Sessions)
The user goes to the **"Connected Portals"** tab. They see a list of platforms:
- **Naukri** `[ Connect ]`
- **Internshala** `[ Connect ]`
- **LinkedIn** `[ Connect ]`

When they click **"Connect"** next to Naukri:
1. An embedded Chrome window pops up inside the app showing the official Naukri login page.
2. The user logs in to their account.
3. The popup closes, and the button changes to a green checkmark: **`[✓] Naukri Connected`**. 
*(The session cookies are saved locally so they never have to log in again).*

---

## Step 5: Start the Engine
The user goes to the main dashboard:
1. They select their active search filters (e.g. *Locations: Bangalore, Mumbai, Remote*).
2. They click the large glowing green button: **"Start EasyApply Engine"**.
3. The app minimizes to the system tray.

---

## Step 6: Background Automation (Running)
While the user plays a game, watches YouTube, or sleeps:
- The Playwright agent runs in the background, crawling Naukri and Internshala.
- It finds a matching React developer opening.
- **Form Filling**: It populates all text inputs, selects options (notice period, experience), and uploads the resume.
- **CAPTCHA Handler**: If Naukri shows a security challenge, a subtle desktop notification pops up: *"EasyApply: Verification required for Naukri. Click here to solve."* The user clicks it, solves the captcha in the pop-up browser, and the bot instantly resumes in the background.
- **Submit**: It submits the application.

---

## Step 7: The Tracking Dashboard (Kanban Board)
When the user opens the desktop app, they see a clean tracker dashboard showing their real-time application pipelines:

```
+------------------+     +------------------+     +------------------+
|   Matches (12)   |     |   Applied (48)   |     |  Interviews (2)  |
+------------------+     +------------------+     +------------------+
| [Google]         |     | [Wipro]          |     | [Apple]          |
| Software Eng     | --> | Frontend Dev     | --> | iOS Engineer     |
| 3 hours ago      |     | Applied 2h ago   |     | Invite Recieved  |
+------------------+     +------------------+     +------------------+
```
- They can click on any card to see the direct URL of the job description, the resume version sent, and the timestamp of when the agent applied.
