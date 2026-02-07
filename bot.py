import asyncio
import random
import re
import os
import json
import requests
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# --- CONFIG FROM ENVIRONMENT VARIABLES (GITHUB SECRETS) ---
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "DefaultPass123!")
SHEET_NAME = os.getenv("SHEET_NAME")
# GitHub Secrets stores the JSON as a string; we convert it back to a dict
GOOGLE_JSON_CREDENTIALS = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

def setup_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(GOOGLE_JSON_CREDENTIALS, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open(SHEET_NAME)
    return sh.get_worksheet(0)

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
                if match: return match.group(0)
    except: pass
    return None

def clean_url(url):
    return url.split('&')[0] if "youtube.com/watch?v=" in url else url

async def process_link(browser, raw_link, row_num, ws):
    timestamp = datetime.now().strftime("%H:%M:%S")
    yt_link = clean_url(raw_link)
    email, sid = get_guerrilla_mail()
    
    # Github Actions runs better with a fresh context per task
    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    page = await context.new_page()
    
    try:
        print(f"[{timestamp}] Row {row_num}: {yt_link} | {email}")
        
        # 1. Reset/Create Account
        await page.goto("https://youdiepie.com/password/reset", timeout=60000)
        await page.fill('input[placeholder*="Email"]', email)
        await page.click('button:has-text("Reset / Generate Password")')

        code = None
        for _ in range(15):
            await asyncio.sleep(7)
            code = fetch_guerrilla_code(sid)
            if code: break
        
        if not code:
            ws.update_cell(row_num, 2, f"{timestamp} - No Email")
            return

        await page.fill('input[placeholder*="1"]', code)
        for p_in in await page.query_selector_all('input[type="password"]'):
            await p_in.fill(FIXED_PASSWORD)
        await page.click('button:has-text("Reset / Generate Password")')
        await asyncio.sleep(5)

        # 2. Order
        await page.goto("https://youdiepie.com/free-youtube-views", timeout=60000)
        await (await page.wait_for_selector('input[type="checkbox"]')).check()
        await page.fill('input[placeholder*="youtube.com/watch"]', yt_link)
        
        await page.keyboard.press("Tab")
        await asyncio.sleep(10) # Wait for site validation
        
        btn = await page.wait_for_selector('button:not(.nav-link):has-text("Checkout"), button:not(.nav-link):has-text("Order")')
        
        if "valid Input" not in await btn.inner_text():
            await btn.click()
            await asyncio.sleep(8)
            ws.update_cell(row_num, 2, f"{timestamp} - Success ({email})")
            print("SUCCESS")
        else:
            ws.update_cell(row_num, 2, f"{timestamp} - Invalid Link")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await context.close()

async def main():
    ws = setup_sheets()
    links = ws.col_values(1)[1:]
    async with async_playwright() as p:
        # Github Actions requires headless=True
        browser = await p.chromium.launch(headless=True)
        for i, link in enumerate(links):
            await process_link(browser, link, i+2, ws)
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
