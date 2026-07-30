import asyncio
import os
import sys
import json
import subprocess
import socket
import time
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drivers.greenhouse import apply_greenhouse
from drivers.smartrecruiters import apply_smartrecruiters
from drivers.zohorecruit import apply_zohorecruit

def is_chrome_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', 9222)) == 0

def launch_chrome():
    if is_chrome_running():
        return
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\chrome-dev-profile"
    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run"
    ])
    print("Waiting for Chrome port 9222 to activate...")
    for _ in range(12):
        if is_chrome_running():
            return
        time.sleep(1)

async def test_driver():
    # 1. Load profile
    profile_path = os.path.join(os.path.dirname(__file__), "profile.json")
    if not os.path.exists(profile_path):
        print(f"Profile not found at: {profile_path}")
        return
        
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
        
    print("\nSelect the driver you want to test:")
    print("1. Greenhouse (Tide Software)")
    print("2. SmartRecruiters (Winbold)")
    print("3. Zoho Recruit (Zyphra Tech)")
    print("4. Exit")
    
    choice = input("Enter choice (1-4): ").strip()
    if choice == "1":
        url = "https://job-boards.greenhouse.io/tide/jobs/7702561003"
        driver_fn = apply_greenhouse
        name = "Greenhouse"
    elif choice == "2":
        url = "https://jobs.smartrecruiters.com/Winbold/744000098688234"
        driver_fn = apply_smartrecruiters
        name = "SmartRecruiters"
    elif choice == "3":
        url = "https://zyphratechsolutions.zohorecruit.in/jobs/Careers/185247000005348426"
        driver_fn = apply_zohorecruit
        name = "Zoho Recruit"
    else:
        print("Exiting.")
        return
        
    print(f"\nStarting {name} driver test against: {url}")
    
    launch_chrome()
    async with async_playwright() as p:
        try:
            # Connect to local Chrome debugging session
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = await context.new_page()
            
            await page.goto(url)
            await page.wait_for_timeout(3000)
            
            success = await driver_fn(page, context, profile)
            if success:
                print(f"\n[SUCCESS] {name} driver executed and filled the form successfully!")
                print("Please check the browser window to verify the details are filled correctly.")
            else:
                print(f"\n[FAILED] {name} driver failed to fill the form.")
                
            input("\nPress Enter to close the page and finish testing...")
            await page.close()
            await browser.close()
            
        except Exception as e:
            print(f"Test execution failed: {e}")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_driver())
