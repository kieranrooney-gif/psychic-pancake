import os
import requests
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai

# Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "last_gazette.txt"

# Initialize the Gemini Client
# It will automatically find the GEMINI_API_KEY in your GitHub Secrets/Env
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_summary(pdf_content):
    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        # Gazette summaries are usually in the first 3 pages
        text = ""
        for i in range(min(3, len(reader.pages))):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text += page_text
        
        # Use 'gemini-2.0-flash-lite' for the best free-tier stability
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite', 
            contents=f"Summarize the key notices from this Victorian Gazette into a concise bulleted list: \n\n{text[:6000]}"
        )
        return response.text
    except Exception as e:
        print(f"AI Summary Error: {e}")
        # If AI fails due to quota, we still want the notification to go through!
        return "⚠️ AI summary hit a quota limit, but the new Gazette is available at the link below."

def send_notification(name, link, summary):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # Using Markdown for a professional look
    msg = f"🗞 *New Gazette Found!*\n{name}\n\n*Key Highlights:*\n{summary}\n\n🔗 [View Full Gazette]({link})"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    
    requests.post(url, data=payload)

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_link_tag = soup.find('a', href=lambda x: x and x.endswith('.pdf'))
    
    if not latest_link_tag:
        print("No PDF links found on page.")
        return
    
    latest_url = BASE_URL + latest_link_tag['href']
    
    # Persistence check (The Bot's Memory)
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            if f.read().strip() == latest_url:
                print("No new gazettes today.")
                return

    print(f"New Gazette detected: {latest_url}")
    pdf_response = requests.get(latest_url)
    
    summary = get_summary(pdf_response.content)
    send_notification(latest_link_tag.text.strip(), latest_url, summary)
    
    # Save progress
    with open(LOG_FILE, 'w') as f:
        f.write(latest_url)

if __name__ == "__main__":
    check_for_updates()
