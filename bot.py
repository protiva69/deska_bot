import requests
from bs4 import BeautifulSoup

# --- NASTAVENÍ ---
TELEGRAM_TOKEN = "TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]" # Bude to vypadat třeba jako "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
CHAT_ID = "722376617"

def posli_telegram_zpravu(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    parametry = {"chat_id": CHAT_ID, "text": text}
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

# --- FINÁLE ---
zprava = f"🔔 Nový dokument na úřední desce!\n\nNázev: {nazev}\nOdkaz: {odkaz}"
posli_telegram_zpravu(zprava)

print("Zpráva byla odeslána na Telegram!")