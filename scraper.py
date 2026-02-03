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

# --- Configuration ---
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "seen_links.txt"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=2, min=5, max=30),
    retry=retry_if_exception_type(errors.ClientError)
)
def get_batch_summary(gazette_data_list):
    if not gazette_data_list:
        return ""

    combined_input = "Briefly summarize the key notices for EACH of these Victorian Special Gazettes in 2-3 bullets:\n\n"
    for item in gazette_data_list:
        combined_input += f"--- GAZETTE: {item['name']} ---\n{item['text_content']}\n\n"

    response = client.models.generate_content(
        model='gemini-2.0-flash-lite', 
        contents=combined_input[:12000]
    )
    return response.text

def send_master_notification(new_gazettes, batch_summary):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # Header
    message = f"🔔 *GAZETTE UPDATE: {datetime.now().strftime('%d %b %Y')}*\n"
    message += f"Found {len(new_gazettes)} new items.\n\n"

    # AI Batch Summary
    if batch_summary:
        message += f"🤖 *AI Summary of Specials:*\n{batch_summary}\n\n"

    # List of Links
    message += "🔗 *Direct Links:*\n"
    for g in new_gazettes:
        emoji = "🚨" if "Special" in g['name'] else "📅"
        message += f"{emoji} [{g['name']}]({g['url']})\n"

    # Send via Telegram (handles long messages)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i in range(0, len(message), 4000):
        requests.post(url, data={"chat_id": chat_id, "text": message[i:i+4000], "parse_mode": "Markdown"})

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

    # 1. Gather all new links from last 7 days
    for link_tag in reversed(all_links):
        full_url = BASE_URL + link_tag['href']
        name = link_tag.text.strip()
        try:
            date_str = name.split("Dated ")[1]
            gazette_date = datetime.strptime(date_str, "%d %B %Y")
            if gazette_date >= seven_days_ago and full_url not in seen_links:
                new_gazettes.append({'name': name, 'url': full_url})
        except: continue

    if not new_gazettes:
        print("No new updates.")
        return

    # 2. Extract content for Specials only
    batch_queue = []
    for g in new_gazettes:
        if "Special" in g['name']:
            try:
                res = requests.get(g['url'])
                reader = PdfReader(io.BytesIO(res.content))
                g['text_content'] = reader.pages[0].extract_text()[:2000]
                batch_queue.append(g)
            except: g['text_content'] = "Could not read PDF."

    # 3. Request Batch Summary
    batch_summary = ""
    if batch_queue:
        try:
            batch_summary = get_batch_summary(batch_queue)
        except: batch_summary = "AI Summary hit quota limit."

    # 4. Notify
    send_master_notification(new_gazettes, batch_summary)

    # 5. Save History
    with open(LOG_FILE, 'w') as f:
        current_seen = seen_links + [g['url'] for g in new_gazettes]
        f.write("\n".join(current_seen[-50:]))

if __name__ == "__main__":
    check_for_updates()
