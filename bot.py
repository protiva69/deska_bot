import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import time
import sys

# --- KONFIGURACE ---
URL_DESKY = "https://www.tyniste.cz/cs/mestsky-urad/uredni-deska-3.html"
BASE_URL = "https://www.tyniste.cz"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SOUBOR_PAMET = "posledni_dokument.txt"

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
        return f"Nepodařilo se vytvořit AI shrnutí. (Chyba: {e})"
    finally:
        for f in uploaded_files:
            genai.delete_file(f.name)

def send_telegram(title, link, summary, pdf_paths):
    print("📱 Odesílám na Telegram...")
    text = f"🔔 *Nový dokument na úřední desce*\n\n📌 *{title}*\n🔗 [Odkaz na detail]({link})\n\n🤖 *AI Shrnutí:*\n{summary}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    
    msg_id = res.json().get("result", {}).get("message_id")

    for pdf in pdf_paths:
        with open(pdf, 'rb') as f:
            url_doc = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
            requests.post(url_doc, data={"chat_id": CHAT_ID, "reply_to_message_id": msg_id}, files={"document": f})

def main():
    print("🕵️ START: Kontroluji úřední desku (verze 3)...")
    sys.stdout.flush()
    
    response = requests.get(URL_DESKY)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Tvůj ověřený způsob hledání v tabulce
    tabulka = soup.find('table', class_='uredni_deska_vypis')
    if not tabulka:
        print("❌ Tabulka 'uredni_deska_vypis' nebyla nalezena!")
        return

    prvni_odkaz = tabulka.find('a')
    if not prvni_odkaz:
        print("❌ V tabulce nebyl nalezen žádný odkaz!")
        return

    nazev = prvni_odkaz.text.strip()
    odkaz = BASE_URL + prvni_odkaz['href']
    
    # Kontrola paměti (podle názvu, jak jsi to měl včera)
    pamatovany_nazev = ""
    if os.path.exists(SOUBOR_PAMET):
        with open(SOUBOR_PAMET, "r", encoding="utf-8") as f:
            pamatovany_nazev = f.read().strip()
            
    if nazev == pamatovany_nazev:
        print("✅ Na desce není nic nového.")
        return

    print(f"🆕 Nalezena novinka: {nazev}")
    
    # Přejdeme na detail pro stažení PDF
    detail_res = requests.get(odkaz)
    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
    
    pdf_links = []
    for a in detail_soup.find_all('a', href=True):
        if a['href'].lower().endswith('.pdf'):
            full_pdf_url = a['href'] if a['href'].startswith('http') else BASE_URL + a['href']
            if full_pdf_url not in pdf_links: # duplicita
                pdf_links.append(full_pdf_url)
    
    stazene_soubory = []
    for i, pdf_url in enumerate(pdf_links):
        path = f"priloha_{i}.pdf"
        r = requests.get(pdf_url)
        with open(path, 'wb') as f:
            f.write(r.content)
        stazene_soubory.append(path)
        
    # AI a odeslání
    summary = get_ai_summary(stazene_soubory)
    send_telegram(nazev, odkaz, summary, stazene_soubory)
    
    # Uložení nového názvu do paměti
    with open(SOUBOR_PAMET, "w", encoding="utf-8") as f:
        f.write(nazev)
        
    # Úklid
    for f in stazene_soubory:
        os.remove(f)
    print("✅ Vše hotovo a uloženo!")

if __name__ == "__main__":
    main()
