import os
import sys
import json
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
import pdfkit
import pandas as pd
import smtplib
from email.message import EmailMessage

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")
TEMPLATE_DIR = os.path.join(BASE, "script", "templates")

# ================= CONFIG WKHTML =================

config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

# ================= LETTURA DATI =================

data = json.loads(sys.argv[1])

cliente = data["cliente"]
pedane = data["pedane"]
lotti = data["lotti"]

aspetto = "+".join([f"(1x{colli} colli)" for colli in pedane])

from collections import defaultdict
lotti_raggruppati = defaultdict(int)

for lotto in lotti:

    data_lotto = lotto.get("data")
    colli = int(lotto.get("colli", 0))

    if not data_lotto:
        continue

    lotti_raggruppati[data_lotto] += colli
print("PEDANE:", pedane)
print("LOTTI:", lotti)
print("RAGGRUPPATI:", lotti_raggruppati)
# ================= LETTURA CLIENTI GDO =================

file_clienti = os.path.join(CONFIG, "CLIENTI_GDO.xlsx")

indirizzo = ""
citta = ""

df = pd.read_excel(file_clienti)

row = df[df["RagioneSociale"].astype(str).str.lower().str.strip() == cliente.lower().strip()]

if not row.empty:

    indirizzo = row.iloc[0]["Via"]
    citta = row.iloc[0]["Citta"]
    piva = row.iloc[0]["PIVA"]

    cliente_consegna = row.iloc[0]["Cliente_Consegna"]
    consegna_via = row.iloc[0]["Consegna_Via"]
    consegna_citta = row.iloc[0]["Consegna_Citta"]
    citta = citta
    email_cliente = row.iloc[0]["Email"]

# ================= CONTATORE DDT =================

contatore = os.path.join(CONFIG, "contatore_ddt.txt")

# crea file se non esiste
if not os.path.exists(contatore):
    with open(contatore, "w") as f:
        f.write("1")

# lettura sicura
try:
    with open(contatore, "r") as f:
        numero = int(f.read().strip())
except:
    numero = 1

num_str = str(numero).zfill(3)

print("📌 NUMERO ATTUALE:", numero)
oggi = datetime.now().strftime("%d/%m/%Y")

# ================= ELABORAZIONE DATI GDO =================

prodotti_render = []

for lotto, colli_totali in lotti_raggruppati.items():

    if not lotto or lotto in ["None", ""]:
        continue

    confezioni = colli_totali * 12

    lotto_dt = datetime.strptime(lotto, "%Y-%m-%d")
    lotto_fmt = lotto_dt.strftime("%d/%m/%y")

    scadenza = (lotto_dt + timedelta(days=28)).strftime("%d/%m/%y")

    descrizione = f"Conf x 6 uova linea l'ov - Lotto {lotto_fmt} - Scad {scadenza}"

    prodotti_render.append({
        "qta": confezioni,
        "descrizione": descrizione,
        "prezzo": ""
    })

# ================= PEDANE =================

numero_pedane = len(pedane)

prodotti_render.append({
    "qta": numero_pedane,
    "descrizione": "Pedane EPAL a rendere",
    "prezzo": ""
})

# ================= ASPETTO ESTERIORE =================

aspetto_esterno = " + ".join([f"(1x {p} colli)" for p in pedane])

colli = sum(int(p) for p in pedane)

# ================= TEMPLATE =================

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template = env.get_template("ddt_gdo.html")

def file_uri(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")

timbro = file_uri(os.path.join(CONFIG, "timbro.png"))
firma_path = os.path.join(CONFIG, f"firma_{data.get('telefono')}.png")

if os.path.exists(firma_path):
    firma_cliente = file_uri(firma_path)
else:
    firma_cliente = None
    
    

html = template.render(

    numero=num_str,
    data=oggi,

    cliente=cliente,
    indirizzo=indirizzo,
    citta=citta,

    prodotti=prodotti_render,

    totale="",

    colli=colli,

    peso_totale="",

    mostra_totale=False,

    testo_pagamento="",

    timbro=timbro,

    firma=None,

    firma_cliente=firma_cliente,

    mostra_sospeso=False,

    saldo_precedente=False,

    saldato=False,

    aspetto_esterno=aspetto_esterno,
    piva=piva,
    cliente_consegna=cliente_consegna,
    consegna_via=consegna_via,
    consegna_citta=consegna_citta,
    aspetto=aspetto

)
def invia_email(destinatario, pdf_path, cliente, numero):

    mittente = "consegne.tuorlobiancofiore@gmail.com"
    password = "uisi wkyd icbo mhth"

    msg = EmailMessage()
    msg["Subject"] = f"DDT {numero} - Tuorlo BiancoFiore"
    msg["From"] = mittente
    msg["To"] = destinatario

    msg.set_content(
        f"""Buongiorno,

in allegato il Documento di Trasporto n. {numero}.

Cordiali saluti
TuorloBiancofiore
"""
    )

    with open(pdf_path, "rb") as f:
        file_data = f.read()

    msg.add_attachment(
        file_data,
        maintype="application",
        subtype="pdf",
        filename=os.path.basename(pdf_path)
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mittente, password)
        smtp.send_message(msg)
# ================= CREA PDF =================

# ================= CARTELLA UNICA =================

anno = datetime.now().strftime("%Y")

# ================= CARTELLA ARCHIVIO =================

from datetime import datetime

oggi = datetime.now()

anno = oggi.strftime("%Y")
mese_num = oggi.strftime("%m")

mesi = [
"gennaio","febbraio","marzo","aprile","maggio","giugno",
"luglio","agosto","settembre","ottobre","novembre","dicembre"
]

mese_nome = mesi[int(mese_num)-1]

cartella_mese = f"{mese_num}_{mese_nome}"

# 📂 percorso finale
dest_dir = os.path.join(
    BASE,
    "RIEPILOGO_DDT",
    f"{anno}_GDO",
    cartella_mese
)

os.makedirs(dest_dir, exist_ok=True)

# ================= FILE HTML TEMP =================

html_path = os.path.join(dest_dir, f"temp_gdo_{num_str}.html")


with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

# ================= PDF FINALE =================

cliente_clean = cliente.replace(" ", "_").replace("/", "").replace("\\", "")

pdf_path = os.path.join(
    dest_dir,
    f"DDT_GDO_{num_str}_{cliente_clean}.pdf"
)

print("DDT GDO CREATO")
print(pdf_path)

# ================= CREA PDF =================

try:

    pdfkit.from_file(
        html_path,
        pdf_path,
        configuration=config,
        options={"enable-local-file-access": None}
    )

    print("✅ PDF CREATO:", pdf_path)

    # ================= AGGIORNA CONTATORE =================

    numero += 1

    with open(contatore, "w") as f:
        f.write(str(numero))

    print("🔢 CONTATORE AGGIORNATO A:", numero)

except Exception as e:
    print("❌ ERRORE CREAZIONE PDF:", e)
    sys.exit()   # 🔥 blocca tutto se fallisce

print("🔢 CONTATORE AGGIORNATO A:", numero)
# ================= COPIA IN OUTPUT_PDF =================

output_pdf_dir = os.path.join(BASE, "output_pdf")
os.makedirs(output_pdf_dir, exist_ok=True)

pdf_output = os.path.join(
    output_pdf_dir,
    f"DDT_GDO_{num_str}_{cliente_clean}_firmato.pdf"
)

import shutil
shutil.copy(pdf_path, pdf_output)

print("📄 Copia PDF in output_pdf:", pdf_output)

try:
    if email_cliente:
        invia_email(email_cliente, pdf_path, cliente, num_str)
        print("Email inviata a:", email_cliente)
except Exception as e:
    print("Errore invio email:", e)
os.remove(html_path)

# apre il pdf solo se esiste davvero
if os.path.exists(pdf_path):
    os.startfile(pdf_path)
else:
    print("Errore: PDF non trovato", pdf_path)