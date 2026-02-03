import os
import requests
import io
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai

# Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "seen_links.txt"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.genai import errors

# This decorator tells the function to keep trying if it hits a quota limit
@retry(
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(errors.ClientError)
)
def get_summary_with_retry(pdf_content):
    reader = PdfReader(io.BytesIO(pdf_content))
    # Reduce page count to 2 to stay under token limits
    text = ""
    for i in range(min(2, len(reader.pages))):
        page_text = reader.pages[i].extract_text()
        if page_text: text += page_text
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite', 
        contents=f"Summarize this Gazette in 3 bullets: \n\n{text[:4000]}"
    )
    return response.text

def send_notification(name, link, summary):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    # Add an emoji based on type
    emoji = "🔴 URGENT:" if "Special" in name else "📅 WEEKLY:"
    msg = f"{emoji} *{name}*\n\n*Summary:*\n{summary}\n\n🔗 [Open PDF]({link})"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Find all links that look like Gazettes
    all_links = soup.find_all('a', href=lambda x: x and x.endswith('.pdf'))
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            seen_links = f.read().splitlines()
    else:
        seen_links = []

    # 2. Filter for Gazettes from the last 7 days
    # This ensures we catch the Weekly (General) even if 20 Specials come out
    new_found = False
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)

    # Process from oldest to newest to keep Telegram chronological
    for link_tag in reversed(all_links):
        full_url = BASE_URL + link_tag['href']
        link_text = link_tag.text.strip()
        
        # Try to parse the date from the text (e.g., "29 January 2026")
        try:
            # Splits "General Gazette Number G5 Dated 29 January 2026"
            date_str = link_text.split("Dated ")[1]
            gazette_date = datetime.strptime(date_str, "%d %B %Y")
        except:
            continue # Skip links that don't match the date format

        # 3. Only process if it's recent AND not seen
        if gazette_date >= seven_days_ago and full_url not in seen_links:
            print(f"New Gazette found: {link_text}")
            pdf_response = requests.get(full_url)
            summary = get_summary(pdf_response.content)
            
            send_notification(link_text, full_url, summary)
            
            seen_links.append(full_url)
            new_found = True
            time.sleep(2) # Avoid Telegram rate limits

    if new_found:
        with open(LOG_FILE, 'w') as f:
            f.write("\n".join(seen_links[-50:])) # Keep a longer history
    else:
        print("No new recent gazettes found.")

if __name__ == "__main__":
    check_for_updates()
