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
    try:
        return gc.open(name).get_worksheet(0)
    except Exception as e:
        print(f"❌ Sheet Error: {e}")
        raise e

def get_guerrilla_mail(retries=3):
    for attempt in range(retries):
        try:
            res = requests.get("https://www.guerrillamail.com/ajax.php?f=get_email_address", timeout=10).json()
            return res['email_addr'], res['sid_token']
        except Exception as e:
            print(f"⚠️ Guerrilla Mail attempt {attempt+1} failed... retrying")
            time.sleep(2)
    return None, None

def fetch_guerrilla_code(sid):
    try:
        res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid}", timeout=10).json()
        if res.get('list'):
            for msg in res['list']:
                full_res = requests.get(f"https://www.guerrillamail.com/ajax.php?f=fetch_email&email_id={msg['mail_id']}&sid_token={sid}").json()
                match = re.search(r'\b\d{6}\b', full_res.get('mail_body', ''))
                if match and match.group(0) not in ["333333", "123456"]:
                    return match.group(0)
    except: pass
    return None

async def human_type(element, text):
    for char in text:
        await element.type(char, delay=random.randint(30, 70))

async def main():
    ws = setup_sheets(SHEET_NAME)
    links = ws.col_values(1)[1:] 
    print(f"🚀 Processing {len(links)} targets. Recording video enabled.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 🎥 VIDEO RECORDING SETTINGS
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            record_video_dir="recordings/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        for i, yt_link in enumerate(links):
            row_num = i + 2
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            email, sid = get_guerrilla_mail()
            if not email:
                print(f"[{i+1}] ❌ Email fail. Skipping.")
                continue

            try:
                print(f"[{i+1}] {email} -> {yt_link}")
                
                await page.goto("https://youdiepie.com/password/reset", timeout=60000)
                await human_type(await page.wait_for_selector('input[placeholder*="Email"]'), email)
                await page.click('button:has-text("Reset / Generate Password")')

                # ⏱️ STEP 1 FIX: INCREASED OTP WAIT (20 loops = 120 seconds)
                code = None
                for _ in range(20): 
                    await asyncio.sleep(6)
                    code = fetch_guerrilla_code(sid)
                    if code: break

                if not code:
                    print(f"   ⚠️ OTP Timeout")
                    ws.update_cell(row_num, 2, f"{timestamp} - Timeout (No OTP)")
                    continue

                await (await page.wait_for_selector('input[placeholder*="1"]')).fill(code)
                for p_in in await page.query_selector_all('input[type="password"]'):
                    await p_in.fill(FIXED_PASSWORD)
                await page.click('button:has-text("Reset / Generate Password")')
                await asyncio.sleep(5)

                # Claim Views
                await page.goto("https://youdiepie.com/free-youtube-views", timeout=60000)
                await (await page.wait_for_selector('input[type="checkbox"]')).check()
                
                yt_in = await page.wait_for_selector('input[placeholder*="youtube.com/watch"]')
                await yt_in.click(click_count=3)
                await page.keyboard.press("Backspace")
                await human_type(yt_in, yt_link)
                await page.keyboard.press("Tab")
                
                # ⏱️ STEP 2 FIX: Increased verification wait to 10s
                await asyncio.sleep(10) 

                submit_btn = await page.wait_for_selector('button:not(.nav-link):has-text("Checkout"), button:not(.nav-link):has-text("Order")', timeout=10000)
                await submit_btn.click(force=True)

                # Finalize
                try:
                    # Look for success indicators or the "Order History" page
                    await page.wait_for_selector('.order-list, text=Success, text=My Orders', timeout=15000)
                    ws.update_cell(row_num, 2, f"{timestamp} - Success ({email})")
                    print(f"   ✅ Success")
                except:
                    print(f"   ⚠️ Status Unknown - Taking Screenshot")
                    await page.screenshot(path=f"error_row_{row_num}.png")
                    ws.update_cell(row_num, 2, f"{timestamp} - Status Unknown")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                ws.update_cell(row_num, 2, f"{timestamp} - Execution Error")

            await context.clear_cookies()
            await asyncio.sleep(2)

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
