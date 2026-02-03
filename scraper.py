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
    retry_if_exception=retry_if_exception_type(errors.ClientError)
)
def get_batch_summary(gazette_data_list):
    """
    Takes a list of dicts [{'name': '...', 'content': '...'}] 
    and returns a single batch summary.
    """
    if not gazette_data_list:
        return {}

    # Combine all texts with clear separators
    combined_input = "Please provide a brief 2-3 bullet point summary for EACH of the following Victorian Special Gazettes:\n\n"
    for item in gazette_data_list:
        combined_input += f"--- DOCUMENT: {item['name']} ---\n{item['text_content']}\n\n"

    response = client.models.generate_content(
        model='gemini-2.0-flash-lite', 
        contents=combined_input[:12000] # Safe limit for free tier tokens
    )
    return response.text

def send_notification(name, link, summary=None):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    emoji = "🚨 *URGENT SPECIAL GAZETTE*" if "Special" in name else "📅 *WEEKLY GENERAL GAZETTE*"
    summary_text = f"\n*Summary:*\n{summary}" if summary else ""
    
    msg = f"{emoji}\n{name}\n{summary_text}\n\n🔗 [Open PDF]({link})"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    all_links = soup.find_all('a', href=lambda x: x and x.endswith('.pdf'))
    
    seen_links = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            seen_links = f.read().splitlines()

    new_gazettes = []
    seven_days_ago = datetime.now() - timedelta(days=7)

    # 1. Collect all new gazettes first
    for link_tag in reversed(all_links):
        full_url = BASE_URL + link_tag['href']
        name = link_tag.text.strip()
        
        try:
            date_str = name.split("Dated ")[1]
            gazette_date = datetime.strptime(date_str, "%d %B %Y")
        except: continue

        if gazette_date >= seven_days_ago and full_url not in seen_links:
            new_gazettes.append({'name': name, 'url': full_url})

    if not new_gazettes:
        print("No new updates.")
        return

    # 2. Extract text for Specials (for batching)
    batch_queue = []
    for g in new_gazettes:
        if "Special" in g['name']:
            print(f"Reading Special: {g['name']}")
            pdf_res = requests.get(g['url'])
            reader = PdfReader(io.BytesIO(pdf_res.content))
            # Just grab first page text for the batch
            g['text_content'] = reader.pages[0].extract_text()[:2000]
            batch_queue.append(g)

    # 3. Get ONE summary for all Specials
    full_batch_report = ""
    if batch_queue:
        print("Sending batch request to AI...")
        full_batch_report = get_batch_summary(batch_queue)

    # 4. Send individual Telegram alerts
    for g in new_gazettes:
        send_notification(g['name'], g['url'], full_batch_report if "Special" in g['name'] else None)
        seen_links.append(g['url'])
        time.sleep(1) # Gentle pace for Telegram

    # 5. Save Memory
    with open(LOG_FILE, 'w') as f:
        f.write("\n".join(seen_links[-50:]))

if __name__ == "__main__":
    check_for_updates()
