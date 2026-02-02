import os
import requests
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai # This is the new 2nd Gen library

# Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "last_gazette.txt"

# Initialize the New Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_summary(pdf_content):
    # Extract text from the first 5 pages
    reader = PdfReader(io.BytesIO(pdf_content))
    text = ""
    for i in range(min(5, len(reader.pages))):
        text += reader.pages[i].extract_text()
    
    prompt = "Summarize this Victorian Government Gazette into bullet points. Focus on major notices or planning changes."
    
    # Updated Model Name: gemini-2.0-flash
    response = client.models.generate_content(
        model='gemini-2.0-flash', 
        contents=f"{prompt}\n\n{text[:10000]}"
    )
    return response.text

def send_notification(name, link, summary):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    msg = f"🗞 *New Gazette Published!*\n{name}\n\n*AI Summary:*\n{summary}\n\n[Full PDF Link]({link})"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    latest_link_tag = soup.find('a', href=lambda x: x and x.endswith('.pdf'))
    
    if not latest_link_tag: return
    
    latest_url = BASE_URL + latest_link_tag['href']
    
    # Memory check
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            if f.read().strip() == latest_url:
                print("No new updates.")
                return

    print(f"New Gazette found! Summarizing...")
    pdf_response = requests.get(latest_url)
    summary = get_summary(pdf_response.content)
    
    send_notification(latest_link_tag.text.strip(), latest_url, summary)
    
    with open(LOG_FILE, 'w') as f:
        f.write(latest_url)

if __name__ == "__main__":
    check_for_updates()
