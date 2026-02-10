import asyncio
import random
import re
import os
import json
import requests
from datetime import datetime
import gspread
from google.oauth2.credentials import Credentials
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
# These will be pulled from your GitHub Secrets
FIXED_PASSWORD = os.getenv("FIXED_PASSWORD", "APNK@2901")
SHEET_NAME = os.getenv("SHEET_NAME", "YoutubeBotLinks")

# --- GOOGLE SHEETS SETUP ---
def setup_sheets(name):
    # Retrieve the token JSON string from GitHub Secrets
    token_json = os.getenv("GOOGLE_TOKEN")
    if not token_json:
        raise ValueError("GOOGLE_TOKEN secret is missing in GitHub!")
    
    token_data = json.loads(token_json)
    
    # Reconstruct credentials from your Colab output
    creds = Credentials.from_authorized_user_info(token_data)
    
    # Authorize and open the sheet
    gc = gspread.authorize(creds)
    sh = gc.open(name)
    return sh.get_worksheet(0)

# --- GUERRILLA MAIL HELPERS ---
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
    # Get all links from Column 1
    links = ws.col_values(1)[1:] 
    print(f"✅ Loaded {len(links)} links. Starting automation...")

    async with async_playwright() as p:
        # Headless MUST be True for GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for i, yt_link in enumerate(links):
            row_num = i + 2
            timestamp = datetime.now().strftime("%H:%M:%S
