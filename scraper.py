import requests
from bs4 import BeautifulSoup
import os

# 1. Configuration
URL = "https://www.gazette.vic.gov.au/gazette_bin/gazette_archives.cfm?bct=home|recentgazettes|gazettearchives"
BASE_URL = "https://www.gazette.vic.gov.au"
LOG_FILE = "last_gazette.txt"

def check_for_updates():
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the first PDF link in the archive list
    latest_link_tag = soup.find('a', href=lambda x: x and x.endswith('.pdf'))
    if not latest_link_tag:
        print("Could not find any gazette links.")
        return

    latest_url = BASE_URL + latest_link_tag['href']
    gazette_name = latest_link_tag.text.strip()

    # 2. Check if this is new
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            last_url = f.read().strip()
    else:
        last_url = ""

    if latest_url != last_url:
        print(f"NEW GAZETTE FOUND: {gazette_name}")
        # Update our record
        with open(LOG_FILE, 'w') as f:
            f.write(latest_url)
        
        # 3. Send notification (We'll use a simple print here; see Step 4 for real alerts)
        send_notification(gazette_name, latest_url)
    else:
        print("No new gazettes today.")

def send_notification(name, link):
    token = "7697048233:AAEE-m1V1cXDeJhipbFaYimX_K-qxJWKCVs"
    chat_id = "t.me/Gazzy26bot."
    msg = f"🗞 New Gazette Published!\n{name}\nLink: {link}"
    requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}")

if __name__ == "__main__":
    check_for_updates()
