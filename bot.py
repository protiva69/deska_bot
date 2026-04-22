import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import time
import sys

# --- NASTAVENÍ ---
URL_DESKY = "https://www.tyniste.cz/mesto/uredni-deska/"
BASE_URL = "https://www.tyniste.cz"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Inicializace Gemini
genai.configure(api_key=GEMINI_KEY)

def get_ai_summary(pdf_paths):
    if not pdf_paths:
        return "K tomuto oznámení nejsou připojeny žádné PDF dokumenty."
    
    print(f"🤖 AI analyzuje {len(pdf_paths)} souborů...")
    uploaded_files = []
    try:
        for path in pdf_paths:
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
        
        time.sleep(2)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = "Přečti si tyto úřední dokumenty a napiš stručné shrnutí (max 4 věty). Co je nejdůležitější pro občana? Piš česky."
        response = model.generate_content(uploaded_files + [prompt])
        return response.text
    except Exception as e:
        return f"Nepodařilo se vytvořit AI shrnutí. ({e})"
    finally:
        for f in uploaded_files:
            genai.delete_file(f.name)

def send_telegram(title, link, summary, pdf_paths):
    print("📱 Odesílám na Telegram...")
    text = f"🔔 *Nová zpráva z úřední desky*\n\n📌 *{title}*\n🔗 [Odkaz na web]({link})\n\n🤖 *AI Shrnutí:*\n{summary}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    
    msg_id = res.json().get("result", {}).get("message_id")

    for pdf in pdf_paths:
        with open(pdf, 'rb') as f:
            url_doc = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
            requests.post(url_doc, data={"chat_id": CHAT_ID, "reply_to_message_id": msg_id}, files={"document": f})

def main():
    # Tento print MUSÍŠ vidět v logu!
    print("🕵️ START: Kontroluji úřední desku...")
    sys.stdout.flush() # Vynutí okamžitý výpis do logu
    
    response = requests.get(URL_DESKY)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    title_el = None
    first_item = soup.find('div', class_='list-item')
    
    if first_item:
        title_el = first_item.find('a')
    else:
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.text.strip()
            if 'mesto/uredni-deska' in href and text and len(text) > 5 and href.strip('/') != 'mesto/uredni-deska':
                title_el = a
                break

    if not title_el:
        print("❌ Nepodařilo se načíst obsah desky.")
        return

    title = title_el.text.strip()
    link = title_el['href'] if title_el['href'].startswith('http') else BASE_URL + title_el['href']
    
    last_link = ""
    if os.path.exists("posledni_dokument.txt"):
        with open("posledni_dokument.txt", "r") as f:
            last_link = f.read().strip()
            
    if link == last_link:
        print("✅ Žádná nová zpráva.")
        return

    print(f"🆕 Nalezena novinka: {title}")
    
    detail_res = requests.get(link)
    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
    
    pdf_links = []
    for a in detail_soup.find_all('a', href=True):
        if a['href'].lower().endswith('.pdf'):
            pdf_link = a['href'] if a['href'].startswith('http') else BASE_URL + a['href']
            pdf_links.append(pdf_link)
    
    stazene_soubory = []
    for i, pdf_url in enumerate(pdf_links):
        path = f"soubor_{i}.pdf"
        r = requests.get(pdf_url)
        with open(path, 'wb') as f:
            f.write(r.content)
        stazene_soubory.append(path)
        
    summary = get_ai_summary(stazene_soubory)
    send_telegram(title, link, summary, stazene_soubory)
    
    with open("posledni_dokument.txt", "w") as f:
        f.write(link)
        
    for f in stazene_soubory:
        os.remove(f)
    print("✅ HOTOVO!")

# TOTO JE NEJDŮLEŽITĚJŠÍ ČÁST - BEZ NÍ SE KÓD NESPPUSTÍ!
if __name__ == "__main__":
    main()
