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

config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

# ================= INPUT =================

data = json.loads(sys.argv[1])

cliente = data["cliente"]
pedane = data["pedane"]
lotti = data["lotti"]
numero_ordine = data.get("numero_ordine","")

# ================= CLIENTI MAIORA =================

file_clienti = os.path.join(CONFIG, "clienti_maiora.xlsx")

df = pd.read_excel(file_clienti)

df.columns = df.columns.str.strip()

row = df[df["Nome"].astype(str).str.strip().str.lower() == cliente.lower().strip()]
email_cliente = ""

if not row.empty:
    email_cliente = str(row.iloc[0].get("Email","")).strip()

if row.empty:
    print("❌ Cliente non trovato")
    sys.exit()

r = row.iloc[0]

indirizzo = r.get("Sede","")
citta = r.get("Città", r.get("Citta",""))
piva = r.get("Piva","")

# ================= MITTENTE FISSO =================

mittente_nome = "MAIORA SPA SB"
mittente_indirizzo = "VIA S.MAGNO 31"
mittente_citta = "CORATO (BA)"
mittente_piva = "07390770720"

# ================= CONTATORE =================

contatore = os.path.join(CONFIG, "contatore_ddt.txt")

if not os.path.exists(contatore):
    with open(contatore, "w") as f:
        f.write("1")

with open(contatore) as f:
    numero = int(f.read().strip())

num_str = str(numero).zfill(3)
oggi = datetime.now().strftime("%d/%m/%Y")

# ================= LOTTI =================

from collections import defaultdict

lotti_raggruppati = defaultdict(int)

for lotto in (lotti or []) :

    data_lotto = lotto.get("data")
    colli = int(lotto.get("colli", 0))

    if not data_lotto:
        continue

    lotti_raggruppati[data_lotto] += colli

# ================= PRODOTTI =================

prodotti_render = []

for lotto, colli_totali in lotti_raggruppati.items():

    lotto_dt = datetime.strptime(lotto, "%Y-%m-%d")

    lotto_fmt = lotto_dt.strftime("%d/%m/%y")
    scadenza = (lotto_dt + timedelta(days=28)).strftime("%d/%m/%y")

    # 🔥 QUI LA MAGIA
    quantita = colli_totali * 12

    descrizione = f"Conf x 6 uova linea l'ov - Lotto {lotto_fmt} - Scad {scadenza}"

    prodotti_render.append({
        "qta": quantita,
        "descrizione": descrizione,
        "prezzo": ""
    })

# ================= PEDANE =================

prodotti_render.append({
    "qta": len(pedane),
    "descrizione": "Pedane EPAL a rendere",
    "prezzo": ""
})

# ================= TOTALI =================

colli = sum(int(p) for p in pedane)
aspetto_esterno = " + ".join([f"(1x {p} colli)" for p in pedane])

def invia_email(destinatario, pdf_path, cliente, numero):

    mittente = "consegne.tuorlobiancofiore@gmail.com"
    password = "uisi wkyd icbo mhth"

    msg = EmailMessage()
    msg["Subject"] = f"DDT {numero} - MAIORA"
    msg["From"] = mittente
    msg["To"] = destinatario

    msg.set_content(
f"""Buongiorno,

in allegato il Documento di Trasporto n. {numero}.

Cordiali saluti
"""
    )

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path)
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mittente, password)
        smtp.send_message(msg)

# ================= TEMPLATE =================

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template = env.get_template("ddt_maiora.html")

def file_uri(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")

timbro_path = os.path.join(CONFIG, "timbro.png")
timbro = file_uri(timbro_path) if os.path.exists(timbro_path) else ""

# ================= FIRMA =================

firma_path = ""

# cerca firma salvata
# ================= FIRMA CORRETTA =================

telefono = data.get("telefono","")
print("📞 TELEFONO RICEVUTO:", telefono)

if not telefono:
    print("❌ TELEFONO NON PASSATO!")
firma_file = f"firma_{telefono}.png"
firma_path = os.path.join(CONFIG, firma_file)

print("📸 FIRMA PATH:", firma_path)
print("📸 ESISTE:", os.path.exists(firma_path))

firma = file_uri(firma_path) if os.path.exists(firma_path) else ""

html = template.render(

    timbro=timbro,
    numero=num_str,
    data=oggi,

    cliente=cliente,
    indirizzo=indirizzo,
    citta=citta,
    piva=piva,

    prodotti=prodotti_render,
    colli=colli,
    aspetto=aspetto_esterno,

    numero_ordine=numero_ordine,

    mittente_nome=mittente_nome,
    mittente_indirizzo=mittente_indirizzo,
    mittente_citta=mittente_citta,
    mittente_piva=mittente_piva,
    
    firma=firma

)

# ================= ARCHIVIO DDT MAIORA =================

anno = datetime.now().strftime("%Y")
mese_num = datetime.now().strftime("%m")

mesi = [
"gennaio","febbraio","marzo","aprile","maggio","giugno",
"luglio","agosto","settembre","ottobre","novembre","dicembre"
]

mese_nome = mesi[int(mese_num)-1]

cartella_mese = f"{mese_num}_{mese_nome}"

base_archivio = os.path.join(BASE, "RIEPILOGO_DDT")

# 🔥 QUI CAMBIA
cartella_anno = os.path.join(base_archivio, f"{anno}_MAIORA")

dest_dir=os.path.join(cartella_anno, cartella_mese)
cliente_clean = cliente.replace(" ", "_").replace("/", "")
os.makedirs(dest_dir, exist_ok=True)



# ================= PDF =================

html_path = os.path.join(dest_dir, f"temp_maiora_{num_str}.html")

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

cliente_clean = cliente.replace(" ", "_")

pdf_path = os.path.join(
    dest_dir,
    f"DDT_MAIORA_{num_str}_{cliente_clean}.pdf"
)

pdfkit.from_file(
    html_path,
    pdf_path,
    configuration=config,
    options={"enable-local-file-access": None}
)

try:
    if email_cliente and email_cliente.lower() != "nan":
        invia_email(email_cliente, pdf_path, cliente, num_str)
        print("📧 Email inviata a:", email_cliente)
except Exception as e:
    print("Errore invio email:", e)

# aggiorna contatore
numero += 1

with open(contatore, "w") as f:
    f.write(str(numero))

os.remove(html_path)

if os.path.exists(pdf_path):
    os.startfile(pdf_path)
else:
    print("Errore PDF")
    
 