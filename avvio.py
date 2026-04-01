import time
import json
import pandas as pd
import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

print("AVVIO BOT WHATSAPP")

options = webdriver.ChromeOptions()
options.add_argument("--user-data-dir=C:/ChromeProfile")
options.add_argument("--profile-directory=Default")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get("https://web.whatsapp.com")

print("Attendi caricamento...")
time.sleep(15)

# ===== FILE ORDINI =====
ORDINI_FILE = "ORDINI.xlsx"

# ===== PRODOTTI BOT =====
with open("prodotti.json") as f:
    PRODOTTI = json.load(f)

ultimo_messaggio = ""

print("BOT IN ASCOLTO")

while True:
    try:
        # chat con pallino verde (nuovi messaggi)
        chats = driver.find_elements(By.XPATH, '//span[@aria-label=" non letto "]')

        if chats:
            chats[0].click()
            time.sleep(2)

        # prendi tutti i messaggi
        messaggi = driver.find_elements(By.XPATH, '//div[contains(@class,"message-in")]//span[@dir="auto"]')

        if not messaggi:
            time.sleep(5)
            continue

        testo = messaggi[-1].text.strip()

        if testo == ultimo_messaggio:
            time.sleep(3)
            continue

        ultimo_messaggio = testo
        print("NUOVO MESSAGGIO:", testo)

        # ===== SOLO NUMERI =====
        if any(c.isdigit() for c in testo):
            numeri = testo.replace(" ", "").split(",")

            prodotti_ordinati = []
            for n in numeri:
                if n in PRODOTTI:
                    prodotti_ordinati.append(PRODOTTI[n])

            if not prodotti_ordinati:
                print("Nessun prodotto riconosciuto")
                continue

            print("ORDINE:", prodotti_ordinati)

            # ===== NUMERO TELEFONO =====
            telefono = driver.find_element(By.XPATH, '//header//span[@dir="auto"]').text
            telefono = telefono.replace(" ", "")

            print("CLIENTE:", telefono)

            # ===== SALVA IN EXCEL =====
            if os.path.exists(ORDINI_FILE):
                df = pd.read_excel(ORDINI_FILE)
            else:
                df = pd.DataFrame(columns=["Telefono","Prodotto","Quantità","Stato"])

            for p in prodotti_ordinati:
                df.loc[len(df)] = [telefono, p, 1, "nuovo"]

            df.to_excel(ORDINI_FILE, index=False)

            print("SALVATO IN ORDINI")

        time.sleep(3)

    except Exception as e:
        print("ERRORE:", e)
        time.sleep(5)