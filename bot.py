import requests
from bs4 import BeautifulSoup
import os

# --- NASTAVENÍ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") 
CHAT_ID = os.getenv("CHAT_ID")
SOUBOR_PAMET = "posledni_dokument.txt"

def posli_telegram_zpravu(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    parametry = {
        "chat_id": CHAT_ID, 
        "text": text,
        "disable_web_page_preview": "true" 
    }
    requests.get(url, params=parametry)

# --- SCRAPER (Týniště) ---
url_obce = "https://www.tyniste.cz/cs/mestsky-urad/uredni-deska-3.html"
stranka = requests.get(url_obce)
stranka.encoding = 'utf-8'
soup = BeautifulSoup(stranka.text, 'html.parser')

tabulka = soup.find('table', class_='uredni_deska_vypis')
prvni_odkaz = tabulka.find('a')

nazev = prvni_odkaz.text.strip()
odkaz = "https://www.tyniste.cz" + prvni_odkaz['href']

# --- LOGIKA PAMĚTI A ODESLÁNÍ ---
pamatovany_nazev = ""
if os.path.exists(SOUBOR_PAMET):
    with open(SOUBOR_PAMET, "r", encoding="utf-8") as soubor:
        pamatovany_nazev = soubor.read()

if nazev != pamatovany_nazev:
    zprava = f"🔔 Nový dokument na úřední desce!\n\nNázev: {nazev}\nOdkaz: {odkaz}"
    posli_telegram_zpravu(zprava)
    print("Našel jsem nový dokument! Zpráva odeslána na Telegram.")
    
    with open(SOUBOR_PAMET, "w", encoding="utf-8") as soubor:
        soubor.write(nazev)
else:
    print("Na desce není nic nového. Nespamuji na Telegram.")
