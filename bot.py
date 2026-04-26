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

# Přípony které stahujeme a posíláme do Gemini
PODPOROVANE_PRIPONY = {
    ".pdf":  "application/pdf",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt":  "application/vnd.oasis.opendocument.text",
    ".ods":  "application/vnd.oasis.opendocument.spreadsheet",
    ".txt":  "text/plain",
    ".rtf":  "application/rtf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
}

# Inicializace Gemini (nové SDK)
client = genai.Client(api_key=GEMINI_KEY)

def get_ai_summary(soubory):
    """soubory = list of (path, mime_type)"""
    if not soubory:
        return "K tomuto oznámení nejsou připojeny žádné dokumenty."

    print(f"🤖 AI analyzuje {len(soubory)} souborů...")
    uploaded_files = []
    try:
        for path, mime_type in soubory:
            with open(path, "rb") as f:
                uploaded = client.files.upload(
                    file=f,
                    config=types.UploadFileConfig(mime_type=mime_type)
                )
            uploaded_files.append(uploaded)

        time.sleep(2)

        prompt = "Přečti si tyto úřední dokumenty a shrň je do jednoho odstavce. Piš česky, stylem jako když se dva chlapy baví v hospodě u piva – žádný úřednický kecy, normální lidská řeč, klidně trochu sarkasmu nebo nadsázky. Drž se faktů z dokumentu, ale polopaticky a přirozeně."

        contents = [types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type) for f in uploaded_files]
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

def send_telegram(title, link, summary, soubory):
    print("📱 Odesílám na Telegram...")
    text = f"🔔 *Nový dokument na úřední desce*\n\n📌 *{title}*\n🔗 [Odkaz na detail]({link})\n\n🤖 *AI Shrnutí:*\n{summary}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    res = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

    msg_id = res.json().get("result", {}).get("message_id")

    for path, _ in soubory:
        with open(path, 'rb') as f:
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

    prilohy_urls = []
    for a in detail_soup.find_all('a', href=True):
        href_lower = a['href'].lower()
        for pripona, mime_type in PODPOROVANE_PRIPONY.items():
            if href_lower.endswith(pripona):
                full_url = a['href'] if a['href'].startswith('http') else BASE_URL + a['href']
                if full_url not in [u for u, _ in prilohy_urls]:
                    prilohy_urls.append((full_url, mime_type))
                break

    print(f"📎 Nalezeno příloh: {len(prilohy_urls)}")

    stazene_soubory = []
    for i, (url, mime_type) in enumerate(prilohy_urls):
        pripona = url.rsplit('.', 1)[-1].lower()
        path = f"priloha_{i}.{pripona}"
        r = requests.get(url)
        with open(path, 'wb') as f:
            f.write(r.content)
        stazene_soubory.append((path, mime_type))

    summary = get_ai_summary(stazene_soubory)
    send_telegram(nazev, odkaz, summary, stazene_soubory)

    with open(SOUBOR_PAMET, "w", encoding="utf-8") as f:
        f.write(nazev)

    for path, _ in stazene_soubory:
        os.remove(path)
    print("✅ Vše hotovo a uloženo!")

if __name__ == "__main__":
    main()
