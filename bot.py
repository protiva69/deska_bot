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
    # Struktura Týniště: příspěvky jsou v divu s třídou 'list-item'
    first_item = soup.find('div', class_='list-item')
    if not first_item:
        print("❌ Nepodařilo se načíst obsah desky.")
        return

    title_el = first_item.find('a')
    title = title_el.text.strip()
    link = BASE_URL + title_el['href']
    
    # Kontrola historie (aby bot neposílal stejnou věc dokola)
    last_link = ""
    if os.path.exists("last_link.txt"):
        with open("last_link.txt", "r") as f:
            last_link = f.read().strip()
            
    if link == last_link:
        print("✅ Žádná nová zpráva.")
        return

    print(f"🆕 Nalezena novinka: {title}")
    
    # Přejdeme na detail zprávy a najdeme všechna PDF
    detail_res = requests.get(link)
    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
    pdf_links = [BASE_URL + a['href'] for a in detail_soup.find_all('a', href=True) if a['href'].endswith('.pdf')]
    
    stazene_soubory = []
    for i, pdf_url in enumerate(pdf_links):
        path = f"soubor_{i}.pdf"
        with open(path, 'wb') as f:
            f.write(requests.get(pdf_url).content)
        stazene_soubory.append(path)
        
    # AI analýza
    summary = get_ai_summary(stazene_soubory)
    
    # Odeslání
    send_telegram(title, link, summary, stazene_soubory)
    
    # Uložíme si link jako poslední zpracovaný
    with open("last_link.txt", "w") as f:
        f.write(link)
        
    # Smazání lokálních PDF
    for f in stazene_soubory:
        os.remove(f)

if __name__ == "__main__":
    main()
