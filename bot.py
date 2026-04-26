import os
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import time
import sys

# --- KONFIGURACE ---
URL_DESKY = "https://www.tyniste.cz/cs/mestsky-urad/uredni-deska-3.html"
BASE_URL = "https://www.tyniste.cz"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
SOUBOR_PAMET = "posledni_dokument.txt"

# Inicializace Gemini (nové SDK)
client = genai.Client(api_key=GEMINI_KEY)

def get_ai_summary(pdf_paths):
    if not pdf_paths:
        return "K tomuto oznámení nejsou připojeny žádné PDF dokumenty."

    print(f"🤖 AI analyzuje {len(pdf_paths)} souborů...")
    uploaded_files = []
    try:
        for path in pdf_paths:
            with open(path, "rb") as f:
                uploaded = client.files.upload(
                    file=f,
                    config=types.UploadFileConfig(mime_type="application/pdf")
                )
            uploaded_files.append(uploaded)

        time.sleep(2)

        prompt = "Přečti si tyto úřední dokumenty a shrň je do jednoho odstavce. Piš česky, stylem jako když se dva chlapy baví v hospodě u piva – žádný úřednický kecy, normální lidská řeč, klidně trochu sarkasmu nebo nadsázky. Drž se faktů z dokumentu, ale polopaticky a přirozeně."

        contents = [types.Part.from_uri(file_uri=f.uri, mime_type="application/pdf") for f in uploaded_files]
        contents.append(types.Part.from_text(text=prompt))

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents
        )
        return response.text

    except Exception as e:
        return f"Nepodařilo se vytvořit AI shrnutí. (Chyba: {e})"
    finally:
        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass

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
    print("🕵️ START: Kontroluji úřední desku...")
    sys.stdout.flush()

    response = requests.get(URL_DESKY)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

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

    pamatovany_nazev = ""
    if os.path.exists(SOUBOR_PAMET):
        with open(SOUBOR_PAMET, "r", encoding="utf-8") as f:
            pamatovany_nazev = f.read().strip()

    if nazev == pamatovany_nazev:
        print("✅ Na desce není nic nového.")
        return

    print(f"🆕 Nalezena novinka: {nazev}")

    detail_res = requests.get(odkaz)
    detail_soup = BeautifulSoup(detail_res.text, 'html.parser')

    pdf_links = []
    for a in detail_soup.find_all('a', href=True):
        if a['href'].lower().endswith('.pdf'):
            full_pdf_url = a['href'] if a['href'].startswith('http') else BASE_URL + a['href']
            if full_pdf_url not in pdf_links:
                pdf_links.append(full_pdf_url)

    stazene_soubory = []
    for i, pdf_url in enumerate(pdf_links):
        path = f"priloha_{i}.pdf"
        r = requests.get(pdf_url)
        with open(path, 'wb') as f:
            f.write(r.content)
        stazene_soubory.append(path)

    summary = get_ai_summary(stazene_soubory)
    send_telegram(nazev, odkaz, summary, stazene_soubory)

    with open(SOUBOR_PAMET, "w", encoding="utf-8") as f:
        f.write(nazev)

    for f in stazene_soubory:
        os.remove(f)
    print("✅ Vše hotovo a uloženo!")

if __name__ == "__main__":
    main()
