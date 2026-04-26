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

# Povolené Content-Type → (přípona, mime_type pro Gemini)
POVOLENE_TYPY = {
    "application/pdf":                                                              ("pdf",  "application/pdf"),
    "application/msword":                                                           ("doc",  "application/msword"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":     ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "application/vnd.ms-excel":                                                     ("xls",  "application/vnd.ms-excel"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":           ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "application/vnd.oasis.opendocument.text":                                     ("odt",  "application/vnd.oasis.opendocument.text"),
    "application/vnd.oasis.opendocument.spreadsheet":                              ("ods",  "application/vnd.oasis.opendocument.spreadsheet"),
    "text/plain":                                                                   ("txt",  "text/plain"),
    "application/rtf":                                                              ("rtf",  "application/rtf"),
    "image/png":                                                                    ("png",  "image/png"),
    "image/jpeg":                                                                   ("jpg",  "image/jpeg"),
}

# Přípony pro detekci v URL (záloha)
PRIPONY_Z_URL = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}

# Klíčová slova v href která naznačují přílohu
PRILOHA_KLICOVA_SLOVA = ["file.php", "download", "priloha", "attachment", "dokument", "soubor"]

# Inicializace Gemini
client = genai.Client(api_key=GEMINI_KEY)


def je_priloha(href):
    href_lower = href.lower()
    for pripona in PRIPONY_Z_URL:
        if href_lower.endswith(pripona):
            return True
    for slovo in PRILOHA_KLICOVA_SLOVA:
        if slovo in href_lower:
            return True
    return False


def stahni_prilohu(url, index):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()

        ct = r.headers.get("Content-Type", "").split(";")[0].strip().lower()

        # Ignoruj HTML — to jsou stránky, ne dokumenty
        if ct.startswith("text/html"):
            print(f"  ⏭ Přeskočeno (HTML stránka): {url}")
            return None

        if ct in POVOLENE_TYPY:
            pripona, mime_type = POVOLENE_TYPY[ct]
        else:
            # Zkus odhadnout z URL
            url_lower = url.lower()
            pripona = None
            for p in PRIPONY_Z_URL:
                if url_lower.endswith(p):
                    pripona = p.lstrip(".")
                    break
            if not pripona:
                print(f"  ⏭ Přeskočeno (neznámý typ '{ct}'): {url}")
                return None
            mime_type = ct or "application/octet-stream"

        path = f"priloha_{index}.{pripona}"
        with open(path, "wb") as f:
            f.write(r.content)

        print(f"  ✓ Staženo: {path} ({ct})")
        return (path, mime_type)

    except Exception as e:
        print(f"  ✗ Nepodařilo se stáhnout {url}: {e}")
        return None


def get_ai_summary(soubory):
    if not soubory:
        return "K tomuto oznámení nejsou připojeny žádné dokumenty."

    print(f"🤖 AI analyzuje {len(soubory)} souborů...")
    sys.stdout.flush()
    uploaded_files = []
    try:
        for path, mime_type in soubory:
            print(f"  📤 Nahrávám do Gemini: {path} ({mime_type})")
            sys.stdout.flush()
            with open(path, "rb") as f:
                uploaded = client.files.upload(
                    file=f,
                    config=types.UploadFileConfig(mime_type=mime_type)
                )
            print(f"  ✓ Nahráno jako: {uploaded.name}")
            sys.stdout.flush()
            uploaded_files.append(uploaded)

        print("⏳ Čekám 2s a volám model...")
        sys.stdout.flush()
        time.sleep(2)

        prompt = "Přečti si tyto úřední dokumenty a shrň je do jednoho odstavce normální češtinou. Piš tak, aby tomu rozuměl každý běžný člověk bez právního nebo úředního vzdělání. Žádné složité fráze, žádný úřednický jazyk — jen prostě a jasně o čem dokument je a co z toho vyplývá pro občana."

        contents = [types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type) for f in uploaded_files]
        contents.append(types.Part.from_text(text=prompt))

        print("🧠 Generuji shrnutí...")
        sys.stdout.flush()
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b-001",
            contents=contents
        )
        print("✅ Shrnutí hotovo.")
        sys.stdout.flush()
        return response.text

    except Exception as e:
        print(f"❌ CHYBA v get_ai_summary: {type(e).__name__}: {e}")
        sys.stdout.flush()
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
        with open(path, "rb") as f:
            url_doc = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
            requests.post(url_doc, data={"chat_id": CHAT_ID, "reply_to_message_id": msg_id}, files={"document": f})


def main():
    print("🕵️ START: Kontroluji úřední desku...")
    sys.stdout.flush()

    response = requests.get(URL_DESKY)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    tabulka = soup.find("table", class_="uredni_deska_vypis")
    if not tabulka:
        print("❌ Tabulka 'uredni_deska_vypis' nebyla nalezena!")
        return

    prvni_odkaz = tabulka.find("a")
    if not prvni_odkaz:
        print("❌ V tabulce nebyl nalezen žádný odkaz!")
        return

    nazev = prvni_odkaz.text.strip()
    odkaz = BASE_URL + prvni_odkaz["href"]

    pamatovany_nazev = ""
    if os.path.exists(SOUBOR_PAMET):
        with open(SOUBOR_PAMET, "r", encoding="utf-8") as f:
            pamatovany_nazev = f.read().strip()

    if nazev == pamatovany_nazev:
        print("✅ Na desce není nic nového.")
        return

    print(f"🆕 Nalezena novinka: {nazev}")

    detail_res = requests.get(odkaz)
    detail_soup = BeautifulSoup(detail_res.text, "html.parser")

    prilohy_urls = []
    for a in detail_soup.find_all("a", href=True):
        href = a["href"]
        if je_priloha(href):
            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url not in prilohy_urls:
                prilohy_urls.append(full_url)

    print(f"📎 Nalezeno potenciálních příloh: {len(prilohy_urls)}")

    stazene_soubory = []
    for i, url in enumerate(prilohy_urls):
        vysledek = stahni_prilohu(url, i)
        if vysledek:
            stazene_soubory.append(vysledek)

    print(f"📥 Úspěšně staženo dokumentů: {len(stazene_soubory)}")

    summary = get_ai_summary(stazene_soubory)
    send_telegram(nazev, odkaz, summary, stazene_soubory)

    with open(SOUBOR_PAMET, "w", encoding="utf-8") as f:
        f.write(nazev)

    for path, _ in stazene_soubory:
        os.remove(path)
    print("✅ Vše hotovo a uloženo!")


if __name__ == "__main__":
    main()
