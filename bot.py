import asyncio
import random
import re
import os
import json
import requests
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "APNK@2901")
SHEET_NAME = os.getenv("SHEET_NAME", "YoutubeBotLinks")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def setup_sheets(name):
    creds_json = os.getenv("GOOGLE_TOKEN")
    if not creds_json:
        raise ValueError("GOOGLE_TOKEN secret is missing!")
    creds_data = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open(name).get_worksheet(0)

def get_guerrilla_mail():
    try:
        res = requests.get("https://www.guerrillamail.com/ajax.php?f=get_email_address", timeout=10).json()
        return res['email_addr'], res['sid_token']
    except: return None, None

def fetch_guerrilla_code(sid):
    try:
        res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid}", timeout=10).json()
        if res.get('list'):
            for msg in res['list']:
                full_res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=fetch_email&email_id={msg['mail_id']}&sid_token={sid}").json()
                body = full_res.get('mail_body', '')
                match = re.search(r'\b\d{6}\b', body)
                if match and match.group(0) not in ["333333", "123456"]:
                    return match.group(0)
    except: pass
    return None

async def human_type(element, text):
    for char in text:
        await element.type(char, delay=random.randint(40, 90))

async def main():
    ws = setup_sheets(SHEET_NAME)
    links = ws.col_values(1)[1:] 
    print(f"🚀 Loaded {len(links)} links. Cooldown enabled to prevent OTP blocks.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            record_video_dir="recordings/" 
        )
        page = await context.new_page()

        for i, yt_link in enumerate(links):
            row_num = i + 2
            timestamp = datetime.now().strftime("%H:%M:%S")
            email, sid = get_guerrilla_mail()

            if not email:
                print(f"[{i+1}] ❌ Email service error.")
                continue

            try:
                print(f"\n[{i+1}] Processing: {yt_link}")

                # STEP 1: PASSWORD RESET / ACCOUNT CREATION
                await page.goto("https://youdiepie.com/password/reset", timeout=60000)
                await human_type(await page.wait_for_selector('input[placeholder*="Email"]'), email)
                await page.click('button:has-text("Reset / Generate Password")')

                # Wait for OTP
                code = None
                for _ in range(20): 
                    await asyncio.sleep(6)
                    code = fetch_guerrilla_code(sid)
                    if code: break

                if not code:
                    print(f"   ⚠️ No OTP received for {email}")
                    ws.update_cell(row_num, 2, f"{timestamp} - No OTP (Rate Limited?)")
                else:
                    # Set Password
                    await (await page.wait_for_selector('input[placeholder*="1"]')).fill(code)
                    for p_in in await page.query_selector_all('input[type="password"]'):
                        await p_in.fill(FIXED_PASSWORD)
                    await page.click('button:has-text("Reset / Generate Password")')
                    await asyncio.sleep(5)

                    # STEP 2: CLAIM VIEWS
                    await page.goto("https://youdiepie.com/free-youtube-views", timeout=60000)
                    await (await page.wait_for_selector('input[type="checkbox"]')).check()

                    yt_in = await page.wait_for_selector('input[placeholder*="youtube.com/watch"]')
                    await yt_in.click(click_count=3)
                    await page.keyboard.press("Backspace")
                    await human_type(yt_in, yt_link)
                    await page.keyboard.press("Tab")

                    await asyncio.sleep(10) # Validation wait
                    
                    submit_btn = await page.wait_for_selector('button:not(.nav-link):has-text("Checkout"), button:not(.nav-link):has-text("Order")', timeout=15000)
                    await submit_btn.click(force=True)

                    # STEP 3: CONFIRMATION
                    try:
                        await page.wait_for_selector('.order-list, text=My Orders, text=Success', timeout=20000)
                        ws.update_cell(row_num, 2, f"{timestamp} - Success ({email})")
                        print("   ✅ Success")
                    except:
                        await page.screenshot(path=f"error_row_{row_num}.png")
                        ws.update_cell(row_num, 2, f"{timestamp} - Status Unknown")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                ws.update_cell(row_num, 2, f"{timestamp} - Error")

            # --- THE FIX: COOLDOWN ---
            await context.clear_cookies()
            if i < len(links) - 1: # No need to wait after the very last link
                print(f"   ⏳ Waiting 2 minutes before next account to prevent OTP block...")
                await asyncio.sleep(120) 

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
