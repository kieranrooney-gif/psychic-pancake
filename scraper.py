import os
import requests
import io
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai
from google.genai import errors
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "seen_links.txt"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type(errors.ClientError)
)
def get_ai_summary(pdf_content):
    reader = PdfReader(io.BytesIO(pdf_content))
    # For Special Gazettes, 2 pages is plenty
    text = ""
    for i in range(min(2, len(reader.pages))):
        page_text = reader.pages[i].extract_text()
        if page_text: text += page_text
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite', 
        contents=f"Summarize this URGENT Special Gazette in 3 bullet points: \n\n{text[:5000]}"
    )
    return response.text

def send_notification(name, link, summary=None):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if "Special" in name:
        emoji = "🚨 *URGENT SPECIAL GAZETTE*"
        body = f"Summary:\n{summary}" if summary else "Summary unavailable."
    else:
        emoji = "📅 *WEEKLY GENERAL GAZETTE*"
        body = "Note: Standard weekly update. No AI summary generated to save quota."

    msg = f"{emoji}\n{name}\n\n{body}\n\n🔗 [Open PDF]({link})"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    all_links = soup.find_all('a', href=lambda x: x and x.endswith('.pdf'))
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            seen_links = f.read().splitlines()
    else:
        seen_links = []

    new_found = False
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)

    for link_tag in reversed(all_links):
        full_url = BASE_URL + link_tag['href']
        link_text = link_tag.text.strip()
        
        try:
            date_str = link_text.split("Dated ")[1]
            gazette_date = datetime.strptime(date_str, "%d %B %Y")
        except: continue

        if gazette_date >= seven_days_ago and full_url not in seen_links:
            print(f"Processing: {link_text}")
            
            summary = None
            # Only use AI for Special Gazettes to preserve quota
            if "Special" in link_text:
                pdf_res = requests.get(full_url)
                try:
                    summary = get_ai_summary(pdf_res.content)
                except:
                    summary = "AI quota full. Please check PDF manually."

            send_notification(link_text, full_url, summary)
            seen_links.append(full_url)
            new_found = True
            time.sleep(2)

    if new_found:
        with open(LOG_FILE, 'w') as f:
            f.write("\n".join(seen_links[-50:]))

if __name__ == "__main__":
    check_for_updates()
