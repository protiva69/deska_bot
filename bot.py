import os
import requests
from bs4 import BeautifulSoup
import sys
import shutil
import json

# --- KONFIGURACE ---
URL_DESKY = "https://www.tyniste.cz/cs/mestsky-urad/uredni-deska-3.html"
BASE_URL = "https://www.tyniste.cz"
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GROQ_KEY = os.getenv("GROQ_API_KEY")
SOUBOR_PAMET = "posledni_dokumenty.json"

POVOLENE_TYPY = {
    "application/pdf":                                                              ("pdf",  "pdf"),
    "application/msword":                                                           ("doc",  "doc"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":     ("docx", "docx"),
    "application/vnd.ms-excel":                                                     ("xls",  "other"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":           ("xlsx", "other"),
    "application/vnd.oasis.opendocument.text":                                     ("odt",  "other"),
    "application/vnd.oasis.opendocument.spreadsheet":                              ("ods",  "other"),
    "text/plain":                                                                   ("txt",  "txt"),
    "application/rtf":                                                              ("rtf",  "other"),
    "image/png":                                                                    ("png",  "other"),
    "image/jpeg":                                                                   ("jpg",  "other"),
}

PRIPONY_Z_URL = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}
PRILOHA_KLICOVA_SLOVA = ["file.php", "download", "priloha", "attachment", "dokument", "soubor"]


def nacti_pamet():
    if os.path.exists(SOUBOR_PAMET):
        with open(SOUBOR_PAMET, "r", encoding="utf-8") as f:
            return set(json.load(f))
    # Záloha: zkus načíst starý formát
    if os.path.exists("posledni_dokument.txt"):
        with open("posledni_dokument.txt", "r", encoding="utf-8") as f:
            nazev = f.read().strip()
            return {nazev} if nazev else set()
    return set()


def uloz_pamet(nazvy):
    with open(SOUBOR_PAMET, "w", encoding="utf-8") as f:
        json.dump(list(nazvy), f, ensure_ascii=False)


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

        if ct.startswith("text/html"):
            print(f"  ⏭ Přeskočeno (HTML stránka): {url}")
            return None

        if ct in POVOLENE_TYPY:
            pripona, typ = POVOLENE_TYPY[ct]
        else:
            url_lower = url.lower()
            pripona = None
            for p in PRIPONY_Z_URL:
                if url_lower.endswith(p):
                    pripona = p.lstrip(".")
                    break
            if not pripona:
                print(f"  ⏭ Přeskočeno (neznámý typ '{ct}'): {url}")
                return None
            typ = "other"

        path = f"priloha_{index}.{pripona}"
        with open(path, "wb") as f:
            f.write(r.content)

        print(f"  ✓ Staženo: {path} ({ct})")
        return (path, typ)

    except Exception as e:
        print(f"  ✗ Nepodařilo se stáhnout {url}: {e}")
        return None


def extrahuj_text(path, typ):
    try:
        if typ == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip() or None

        elif typ in ("doc", "docx"):
            import docx
            try_path = path
            if path.endswith(".doc"):
                try_path = path + "x"
                shutil.copy(path, try_path)
            try:
                doc = docx.Document(try_path)
                text = "\n".join(p.text for p in doc.paragraphs)
                if try_path != path and os.path.exists(try_path):
                    os.remove(try_path)
                return text.strip() or None
            except Exception:
                if try_path != path and os.path.exists(try_path):
                    os.remove(try_path)
                raise

        elif typ == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip() or None

        else:
            return None

    except Exception as e:
        print(f"  ✗ Chyba při extrakci textu z {path}: {e}")
        return None


def get_ai_summary(soubory):
    if not soubory:
        return "K tomuto oznámení nejsou připojeny žádné dokumenty."

    print(f"🤖 Extrahuji text z {len(soubory)} souborů...")
    sys.stdout.flush()

    texty = []
    nepodporovane = 0
    for path, typ in soubory:
        print(f"  📄 Zpracovávám: {path} (typ: {typ})")
        sys.stdout.flush()
        text = extrahuj_text(path, typ)
        if text:
            texty.append(text[:8000])
        else:
            nepodporovane += 1

    if not texty:
        if nepodporovane > 0:
            return "Přílohy jsou v nepodporovaném formátu — shrnutí nelze vytvořit."
        return "Z příloh se nepodařilo extrahovat žádný text."

    obsah = "\n\n---\n\n".join(texty)
    if len(obsah) > 20000:
        obsah = obsah[:20000] + "...(zkráceno)"

    prompt = f"""Přečti si tento úřední dokument a shrň ho do jednoho odstavce normální češtinou. Piš tak, aby tomu rozuměl každý běžný člověk bez právního nebo úředního vzdělání. Žádné složité fráze, žádný úřednický jazyk — jen prostě a jasně o čem dokument je a co z toho vyplývá pro občana.

Dokument:
{obsah}"""

    print("🧠 Volám Groq API...")
    sys.stdout.flush()

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        text = result["choices"][0]["message"]["content"]
        print("✅ Shrnutí hotovo.")
        sys.stdout.flush()
        return text

    except Exception as e:
        print(f"❌ CHYBA při volání Groq: {type(e).__name__}: {e}")
        sys.stdout.flush()
        return f"Nepodařilo se vytvořit shrnutí. (Chyba: {e})"


def zpracuj_polozku(nazev, odkaz):
    print(f"🆕 Zpracovávám: {nazev}")
    sys.stdout.flush()

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

    # Odeslání na Telegram
    print("📱 Odesílám na Telegram...")
    text = f"🔔 *Nový dokument na úřední desce*\n\n📌 *{nazev}*\n🔗 [Odkaz na detail]({odkaz})\n\n{summary}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    res = requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })
    msg_id = res.json().get("result", {}).get("message_id")

    for path, _ in stazene_soubory:
        with open(path, "rb") as f:
            url_doc = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
            requests.post(url_doc, data={"chat_id": CHAT_ID, "reply_to_message_id": msg_id}, files={"document": f})

    # Úklid
    for path, _ in stazene_soubory:
        if os.path.exists(path):
            os.remove(path)


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

    # Načti všechny položky z tabulky
    polozky = []
    for a in tabulka.find_all("a"):
        nazev = a.text.strip()
        odkaz = BASE_URL + a["href"]
        if nazev:
            polozky.append((nazev, odkaz))

    if not polozky:
        print("❌ V tabulce nebyly nalezeny žádné položky!")
        return

    print(f"📋 Nalezeno položek na desce: {len(polozky)}")

    # Načti paměť
    pamatovane = nacti_pamet()

    # Najdi nové položky (zachovej pořadí — nejstarší nová první)
    nove = [(n, o) for n, o in polozky if n not in pamatovane]

    if not nove:
        print("✅ Na desce není nic nového.")
        return

    print(f"🆕 Nalezeno nových položek: {len(nove)}")

    # Zpracuj každou novou položku
    for nazev, odkaz in nove:
        zpracuj_polozku(nazev, odkaz)

    # Ulož všechny aktuální názvy jako novou paměť
    aktualni_nazvy = {n for n, _ in polozky}
    uloz_pamet(aktualni_nazvy)

    print("✅ Vše hotovo a uloženo!")


if __name__ == "__main__":
    main()
