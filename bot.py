import asyncio
import random
import re
import os
import json
import requests
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "APNK@2901")
SHEET_NAME = os.getenv("SHEET_NAME", "YoutubeBotLinks")

# FIX: Explicitly define scopes to allow EDITING (fixes 403 error)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def setup_sheets(name):
    # It is recommended to put your service account JSON into a secret named GOOGLE_CREDENTIALS
    creds_json = os.getenv("GOOGLE_TOKEN")
    if not creds_json:
        raise ValueError("GOOGLE_TOKEN secret is missing!")
    
    creds_data = json.loads(creds_json)
    # FIX: Use Service Account Credentials with explicit scopes
    creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    gc = gspread.authorize(creds)
    
    try:
        sh = gc.open(name)
        return sh.get_worksheet(0)
    except Exception as e:
        available = [s.title for s in gc.openall()]
        print(f"❌ Error: Could not find sheet '{name}'. Available: {available}")
        raise e

def get_guerrilla_mail():
    try:
        res = requests.get("https://www.guerrillamail.com/ajax.php?f=get_email_address").json()
        return res['email_addr'], res['sid_token']
    except: return None, None

def fetch_guerrilla_code(sid):
    try:
        res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid}").json()
        if res['list']:
            for msg in res['list']:
                m_id = msg['mail_id']
                full_res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=fetch_email&email_id={m_id}&sid_token={sid}").json()
                body = full_res['mail_body']
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
    # Get all rows to avoid NoneType errors during iteration
    all_data = ws.get_all_records()
    print(f"✅ Loaded {len(all_data)} links. Starting...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()

        for i, row in enumerate(all_data):
            row_num = i + 2  # Offset for header and 0-indexing
            yt_link = row.get('Target')
            
            # FIX: Syntax Error in timestamp string literal 
            timestamp = datetime.now().strftime("%H:%M:%S") 
            
            # Generate new burner account email
            email, sid = get_guerrilla_mail()

            # FIX: Skip if email generation failed (prevents NoneType errors)
            if not email:
                print(f"[{i+1}] Skipping: Could not generate burner email.")
                continue

            try:
                print(f"[{i+1}] Target: {yt_link} | Email: {email}")
                
                # --- PASSWORD RESET / ACCOUNT CREATION ---
                await page.goto("https://youdiepie.com/password/reset", timeout=60000)
                await human_type(await page.wait_for_selector('input[placeholder*="Email"]'), email)
                await page.click('button:has-text("Reset / Generate Password")')

                code = None
                for _ in range(15):
                    await asyncio.sleep(6)
                    code = fetch_guerrilla_code(sid)
                    if code: break

                if not code:
                    ws.update_cell(row_num, 2, f"{timestamp} - No OTP")
                    continue

                await (await page.wait_for_selector('input[placeholder*="1"]')).fill(code)
                pws = await page.query_selector_all('input[type="password"]')
                for p_in in pws: await p_in.fill(FIXED_PASSWORD)
                await page.click('button:has-text("Reset / Generate Password")')
                await asyncio.sleep(5)

                # --- PROCESS YOUTUBE LINK ---
                await page.goto("https://youdiepie.com/free-youtube-views", timeout=60000)
                await (await page.wait_for_selector('input[type="checkbox"]')).check()
                yt_in = await page.wait_for_selector('input[placeholder*="youtube.com/watch"]')
                await yt_in.click(click_count=3)
                await page.keyboard.press("Backspace")
                await human_type(yt_in, yt_link)
                await page.keyboard.press("Tab")
                await page.mouse.click(0, 0)
                await asyncio.sleep(12)

                submit_btn = await page.wait_for_selector('button:not(.nav-link):has-text("Checkout"), button:not(.nav-link):has-text("Order")', timeout=15000)
                await submit_btn.click(force=True)

                # --- VERIFY SUCCESS ---
                try:
                    await page.wait_for_selector('.order-list, text=My Orders', timeout=20000)
                    ws.update_cell(row_num, 2, f"{timestamp} - Success ({email})")
                except:
                    ws.update_cell(row_num, 2, f"{timestamp} - Verify Error")

            except Exception as e:
                print(f"Error on row {row_num}: {e}")
                try: ws.update_cell(row_num, 2, f"{timestamp} - Error")
                except: pass

            # Cleanup for next burner account
            await context.clear_cookies()
            await asyncio.sleep(5)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
