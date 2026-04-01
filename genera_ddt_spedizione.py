import os
import sys
import json
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
import pdfkit
import pandas as pd
from email.message import EmailMessage
import smtplib

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")
TEMPLATE_DIR = os.path.join(BASE, "script", "templates")

# ================= LETTURA DATI =================

data=json.loads(sys.argv[1])

cliente=data["cliente"]
# ================= CARICA CLIENTE =================

file_clienti=os.path.join(BASE,"config","clienti_sped.xlsx")

indirizzo=""
citta=""
pagamento=""

try:

    df=pd.read_excel(file_clienti)

    row=df[df["Cliente"].astype(str).str.lower().str.strip()==cliente.lower().strip()]

    if not row.empty:

        indirizzo=row.iloc[0]["Indirizzo"]

        cap=str(row.iloc[0]["CAP"])
        città=row.iloc[0]["Città"]
        prov=row.iloc[0]["Provincia"]
        pagamento=str(row.iloc[0]["Pagamento"]).lower().strip()

        citta=f"{cap} {città} ({prov})"

except Exception as e:
    print("Errore lettura clienti", e)
prodotti=data["prodotti"]

sconto_percentuale=float(data.get("sconto_percentuale",0) or 0)
sconto_importo=float(data.get("sconto_importo",0) or 0)

# ================= PATH =================



config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

# ================= CONTATORE DDT =================

contatore = os.path.join(CONFIG, "contatore_ddt.txt")

if not os.path.exists(contatore):
    with open(contatore, "w") as f:
        f.write("1")

with open(contatore) as f:
    numero=int(f.read().strip())

num_str=str(numero).zfill(3)

oggi=datetime.now().strftime("%d/%m/%Y")

# ================= ARCHIVIO PDF =================

anno=datetime.now().strftime("%Y")
mese=datetime.now().strftime("%m")
nome_mese=datetime.now().strftime("%B")

cartella_mese=f"{mese}_{nome_mese}"

dest_dir=os.path.join(
    BASE,
    "archivio_pdf_spedizioni",
    anno,
    cartella_mese
)

os.makedirs(dest_dir,exist_ok=True)

# ================= ELABORAZIONE PRODOTTI =================

prodotti_render=[]

peso_totale=0
colli=0
totale=0

for p in prodotti:

    prod=str(p["prodotto"]).lower().strip()
    qta=int(float(p["quantita"]))
    prezzo=float(p["prezzo"])

    lotto=p.get("lotto","")
    macellazione=p.get("macellazione","")

    descr=prod
    q_reale=qta
    kg=0

    # ================= CALCOLO PESO =================

    if "nobiluovo" in prod:

        if "doppio" in prod:
            kg=22*qta
        elif "grande" in prod:
            kg=11*qta
        elif "piccolo" in prod:
            kg=5.5*qta
        else:
            kg=9*qta

    elif "novelle" in prod or "lov" in prod or "l'ov" in prod:

        if "grande" in prod:
            kg=8*qta
        else:
            kg=4*qta

    elif "180" in prod:
        kg=11*qta

    elif "carta" in prod:
        kg=1*qta

    elif "conf" in prod:
        kg=0.4*qta

    elif "orecchiette" in prod:
        kg=16*qta

    elif "tagliolini" in prod:
        kg=12*qta

    elif "semola" in prod:
        kg=15*qta

    elif "olio" in prod:

        if "18" in prod:
            kg=17*qta
        else:
            kg=11.5*qta

    # ================= POLLO =================

    if "pollo" in prod:

        kg=float(p.get("kg",0))
        prezzo_kg=float(p["prezzo"])

        prezzo=kg*prezzo_kg

        mac_fmt=""
        lotto_fmt=""
        scad_fmt=""

        if macellazione:
            mac_dt=datetime.strptime(macellazione,"%Y-%m-%d")
            mac_fmt=mac_dt.strftime("%d/%m/%y")
            scad_fmt=(mac_dt+timedelta(days=7)).strftime("%d/%m/%y")

        if lotto:
            lotto_fmt=datetime.strptime(lotto,"%Y-%m-%d").strftime("%d/%m/%y")

        descr=f"Pollo da carne - Lotto {mac_fmt}-{lotto_fmt} - Scad {scad_fmt}"

        prodotti_render.append({
            "qta":f"{kg:.2f} kg",
            "descrizione":descr,
            "peso":f"{kg:.2f} kg",
            "prezzo":f"{prezzo:.2f}"
        })

        peso_totale+=kg
        totale+=prezzo
        colli+=1

        continue


    # ================= UOVA =================

    if any(x in prod for x in ["nobiluovo","novelle","l'ov","lov","180","carta","conf"]):

        if "nobiluovo" in prod:
            pezzi=240 if "doppio" in prod else 120 if "grande" in prod else 60

        elif "novelle" in prod or "lov" in prod or "l'ov" in prod:
            pezzi=144 if "grande" in prod else 72

        elif "180" in prod:
            pezzi=180

        elif "carta" in prod:
            pezzi=30

        elif "conf" in prod:
            pezzi=6

        else:
            pezzi=0

        q_reale=pezzi*qta

        lotto_fmt=""
        scad_fmt=""

        if lotto:
            lotto_dt=datetime.strptime(lotto,"%Y-%m-%d")
            lotto_fmt=lotto_dt.strftime("%d/%m/%y")
            scad_fmt=(lotto_dt+timedelta(days=28)).strftime("%d/%m/%y")

        descr=f"Uova - Lotto {lotto_fmt} - Scad {scad_fmt}"

    # ================= ALTRI PRODOTTI =================

    elif "olio" in prod:

        pezzi=18 if "18" in prod else 12
        q_reale=pezzi*qta
        descr="Bottiglie 0.5L - Lot 10/2025 -- Scad 06/2027"

    elif "tagliolini" in prod:

        pezzi=12
        q_reale=pezzi*qta
        descr="Pacchi di Tagliolini 500g - Lot 15525 -- Scad 05/2028"

    elif "orecchiette" in prod:

        pezzi=16
        q_reale=pezzi*qta
        descr="Pacchi di Orecchiette 500g - Lot 15525 -- Scad 05/2028"

    elif "semola" in prod:

        pezzi=15
        q_reale=pezzi*qta
        descr="Pacchi di Semola 1kg - Lot S170126 -- Scad 07/2026"


    # ================= RIGA PRODOTTO =================

    prodotti_render.append({
        "qta": q_reale,
        "descrizione": descr,
        "peso": f"{kg:.2f} kg",
        "prezzo": f"{prezzo:.2f}"
    })

    peso_totale += kg
    totale += prezzo
    colli += qta


# ================= SCONTO =================

sconto=0

if sconto_percentuale>0:
    sconto=totale*(sconto_percentuale/100)

if sconto_importo>0:
    sconto=sconto_importo

totale_finale=totale-sconto

if sconto>0:

    descr_sconto="Sconto su ordine"

    if data.get("tipo_sconto")=="prodotto":
        descr_sconto="Sconto su prodotto"

    prodotti_render.append({
        "qta":"",
        "descrizione":descr_sconto,
        "peso":"",
        "prezzo":f"-{sconto:.2f}"
    })

# ================= TEMPLATE =================

env=Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template=env.get_template("ddt_spedizioni.html")

def file_uri(path):
    return "file:///"+os.path.abspath(path).replace("\\","/")

timbro=file_uri(os.path.join(CONFIG,"timbro.png"))
firma=file_uri(os.path.join(CONFIG,"firma.png"))

mostra_totale=True
testo_pagamento=""

if pagamento=="bonifico":

    mostra_totale=False
    testo_pagamento="Pagamento: Bonifico bancario"

html = template.render(
    numero=num_str,
    data=oggi,
    cliente=cliente,
    indirizzo=indirizzo,
    citta=citta,
    prodotti=prodotti_render,
    totale=f"{totale_finale:.2f}",
    colli=colli,
    peso_totale=f"{round(peso_totale,2)} kg",
    mostra_totale=mostra_totale,
    testo_pagamento=testo_pagamento,
    timbro=timbro,
    firma=firma,
    firma_cliente=None,
    mostra_sospeso=False,
    saldo_precedente=False,
    saldato=False,
    tipo="spedizione"
)

# ================= CREA PDF =================

html_path=os.path.join(dest_dir,f"temp_sped_{num_str}.html")

with open(html_path,"w",encoding="utf-8") as f:
    f.write(html)

cliente_clean=cliente.replace(" ","_")

pdf_path=os.path.join(
    dest_dir,
    f"DDT_SP{num_str}_{cliente_clean}.pdf"
)

pdfkit.from_file(
    html_path,
    pdf_path,
    configuration=config,
    options={"enable-local-file-access": None}
)
# ================= INVIO MAIL =================

clienti = pd.read_excel(file_clienti)

cliente_row = clienti[
    clienti["Cliente"].astype(str).str.lower().str.strip()
    ==
    cliente.lower().strip()
]

if not cliente_row.empty:

    email = str(cliente_row.iloc[0].get("Email","")).strip()

    if email and email.lower()!="nan":

        mittente="consegne.tuorlobiancofiore@gmail.com"
        password="uisi wkyd icbo mhth"

        msg=EmailMessage()

        msg["Subject"]=f"DDT Spedizione {num_str}"
        msg["From"]=mittente
        msg["To"]=email

        msg.set_content(
            "Gentile cliente,\n\n"
            "In allegato trova il DDT della spedizione.\n\n"
            "Cordiali saluti\n"
            "Tuorlo Bianco Fiore"
        )

        with open(pdf_path,"rb") as f:

            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(pdf_path)
            )

        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:

            smtp.login(mittente,password)
            smtp.send_message(msg)

        print("MAIL INVIATA A",email)

os.remove(html_path)

# ================= AGGIORNA CONTATORE =================

numero+=1

with open(contatore,"w") as f:
    f.write(str(numero))

print("DDT SPEDIZIONE CREATO")
print(pdf_path)

os.startfile(pdf_path)