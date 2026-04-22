import os
import requests
import json
from bs4 import BeautifulSoup
import google.generativeai as genai
import time

# --- NASTAVENÍ ---
URL_DESKY = "https://www.tyniste.cz/mesto/uredni-deska/"
BASE_URL = "https://www.tyniste.cz"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Inicializace Gemini
genai.configure(api_key=GEMINI_KEY)

def get_ai_summary(pdf_paths):
    """Nahraje všechny PDF do Gemini a získá jeden souhrn."""
    if not pdf_paths:
        return "K tomuto oznámení nejsou připojeny žádné PDF dokumenty."
    
    print(f"🤖 AI analyzuje {len(pdf_paths)} souborů...")
    uploaded_files = []
    try:
        for path in pdf_paths:
            # Nahrajeme soubor do Google AI
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
        
        # Počkáme chvilku, než Google soubory zpracuje
        time.sleep(2)

        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = "Přečti si tyto úřední dokumenty a napiš stručné shrnutí (max 4 věty). Co je nejdůležitější pro občana? Piš česky."
        
        response = model.generate_content(uploaded_files + [prompt])
        return response.text
    except Exception as e:
        return f"Nepodařilo se vytvořit AI shrnutí. ({e})"
    finally:
        # Úklid souborů z cloudu Google
        for f in uploaded_files:
            genai.delete_file(f.name)

def send_telegram(title, link, summary, pdf_paths):
    """Pošle textovou zprávu a pak všechny PDF přílohy."""
    # 1. Textová zpráva
    text = f"🔔 *Nová zpráva z úřední desky*\n\n📌 *{title}*\n🔗 [Odkaz na web]({link})\n\n🤖 *AI Shrnutí:*\n{summary}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    
    # Získáme ID zprávy pro odpovědi (reply)
    msg_id = res.json().get("result", {}).get("message_id")

    # 2. Odeslání PDF souborů jako odpovědi pod hlavní zprávu
    for pdf in pdf_paths:
        with open(pdf, 'rb') as f:
            url_doc = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
            requests.post(url_doc, data={"chat_id": CHAT_ID, "reply_to_message_id": msg_id}, files={"document": f})

def main():
    print("🕵️ Kontroluji úřední desku...")
    response = requests.get(URL_DESKY)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Najdeme první (nejnovější) příspěvek na desce
    title_el = None
    first_item = soup.find('div', class_='list-item')
    
    if first_item:
        title_el = first_item.find('a')
    else:
        # ZÁLOŽNÍ PLÁN: Pokud web vypadá jinak, najdeme prostě první odkaz patřící desce
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.text.strip()
            # Hledáme odkaz, který vede do sekce desky, obsahuje text a není to jen odkaz na celou kategorii
            if 'mesto/uredni-deska' in href and text and len(text) > 5 and href.strip('/') != 'mesto/uredni-deska':
                title_el = a
                break

    if not title_el:
        print("❌ Nepodařilo se načíst obsah desky. Web má pravděpodobně jinou strukturu.")
        return

    title = title_el.text.strip()
    
    # Ošetření, aby odkaz byl vždy kompletní
    if title_el['href'].startswith('http'):
        link = title_el['href']
    else:
        link = BASE_URL + title_el['href']
    
    # Kontrola historie přes tvůj soubor "posledni_dokument.txt"
    last_link = ""
    if os.path.exists("posledni_dokument.txt"):
        with open("posledni_dokument.txt", "r") as f:
            last_link = f.read().strip()
            
    if link == last_link:
        print("✅ Žádná nová zpráva.")
        return

    print(f"🆕 Nalezena novinka: {title}")
    
    # Přejdeme na detail zprávy a najdeme všechna PDF
    detail_res = requests.get(link)
    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
    
    # Hledáme odkazy končící na .pdf
    pdf_links = []
    for a in detail
