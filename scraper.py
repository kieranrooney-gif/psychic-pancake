import os
import requests
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai

# Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "seen_links.txt" # We now store multiple links here

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_summary(pdf_content):
    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        text = ""
        for i in range(min(3, len(reader.pages))):
            page_text = reader.pages[i].extract_text()
            if page_text: text += page_text
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite', 
            contents=f"Summarize this Victorian Gazette into 3-5 bullet points: \n\n{text[:6000]}"
        )
        return response.text
    except Exception as e:
        return f"AI Summary unavailable (Error: {str(e)})"

def send_notification(name, link, summary):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    msg = f"🗞 *New Gazette Found!*\n{name}\n\n*Key Highlights:*\n{summary}\n\n🔗 [View Full Gazette]({link})"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Get the top 5 PDF links from the page
    all_links = soup.find_all('a', href=lambda x: x and x.endswith('.pdf'))[:5]
    
    # Load our history of seen links
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            seen_links = f.read().splitlines()
    else:
        seen_links = []

    new_found = False
    
    # Process links from bottom to top (oldest to newest in the top 5)
    for link_tag in reversed(all_links):
        full_url = BASE_URL + link_tag['href']
        
        if full_url not in seen_links:
            print(f"New Gazette detected: {full_url}")
            pdf_response = requests.get(full_url)
            summary = get_summary(pdf_response.content)
            
            send_notification(link_tag.text.strip(), full_url, summary)
            
            # Add to our seen list
            seen_links.append(full_url)
            new_found = True

    # Save updated list (keeping only the last 20 to keep the file small)
    if new_found:
        with open(LOG_FILE, 'w') as f:
            f.write("\n".join(seen_links[-20:]))
    else:
        print("No new updates found in the top 5 links.")

if __name__ == "__main__":
    check_for_updates()
