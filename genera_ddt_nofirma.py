import pandas as pd
import os
import sys
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
import pdfkit
import json
import re

def pezzi_per_cartone(nome_prodotto):

    match = re.search(r"\((\d+)pz\)", nome_prodotto.lower())

    if match:
        return int(match.group(1))

    return 1

# ================= CONFIG WKHTML =================
config = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

telefono = sys.argv[1]

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")
OUTPUT = os.path.join(BASE, "output_pdf")
TEMPLATE_DIR = os.path.join(BASE, "script", "templates")

os.makedirs(OUTPUT, exist_ok=True)

# ================= PAGAMENTO TEMP =================
pagamento_temp = os.path.join(CONFIG, f"pagamento_temp_{telefono}.json")

if os.path.exists(pagamento_temp):
    with open(pagamento_temp) as f:
        pagamento_info = json.load(f)
else:
    pagamento_info = {}

pagato_oggi = float(pagamento_info.get("pagato_oggi", 0))

# ================= FILE EXCEL =================
clienti = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
ordini = pd.read_excel(os.path.join(CONFIG, "ORDINI.xlsx"))
prezzi = pd.read_excel(os.path.join(CONFIG, "PREZZI.xlsx"))
prezzi_speciali = pd.read_excel(os.path.join(CONFIG, "PREZZI_SPECIALI.xlsx"))

clienti["Telefono"] = clienti["Telefono"].astype(str)
ordini["Telefono"] = ordini["Telefono"].astype(str)

ord_cli = ordini[ordini["Telefono"] == telefono]

if "Stato" in ord_cli.columns:
    ord_cli = ord_cli[ord_cli["Stato"] == "nuovo"]

if ord_cli.empty:
    print("Nessun ordine")
    sys.exit()

cliente = clienti[clienti["Telefono"] == telefono].iloc[0]

nome = cliente["Nome"]
def nome_sicuro(testo):
    testo = testo.strip()
    testo = testo.replace(" ", "_")
    testo = re.sub(r"[^A-Za-z0-9_]", "", testo)
    return testo
nome_file_cliente = nome_sicuro(nome)
indirizzo = cliente["Indirizzo"]
paese = str(cliente["Paese"]).strip().lower()
pagamento = str(cliente["Pagamento"]).strip().lower()

# ================= CONTATORE DDT =================
contatore = os.path.join(CONFIG, "contatore_ddt.txt")

if not os.path.exists(contatore):
    with open(contatore, "w") as f:
        f.write("1")

with open(contatore, "r") as f:
    numero = int(f.read().strip())

num_str = str(numero).zfill(3)
oggi = datetime.now().strftime("%d/%m/%Y")

# ================= LOTTO UOVA =================
lotto_file = os.path.join(CONFIG, "lotto.txt")

if not os.path.exists(lotto_file):
    print("ERRORE: lotto non inserito")
    sys.exit()

with open(lotto_file) as f:
    data_lotto_str = f.read().strip()

data_lotto = datetime.strptime(data_lotto_str, "%Y-%m-%d")
lotto_uova = data_lotto.strftime("%d/%m/%y")
scadenza_uova = (data_lotto + timedelta(days=28)).strftime("%d/%m/%y")

prodotti_render = []
colli = 0
totale = 0

# ================= POLLO =================


pollo_raggruppati = {}

for _, r in ord_cli.iterrows():
    sconto_tot=0

    prod = str(r["Prodotto"]).lower().strip()
    qta = int(r["Quantità"])

    q_reale = qta
    descr = prod
    

    # ================= POLLO =================
    if "pollo" in prod:

        kg = float(r.get("Kg", 0))

        lotto_raw = r.get("Lotto", "")
        mac_raw = r.get("Macellazione", "")
        scad_raw = r.get("Scadenza", "")

        lotto_fmt = ""
        mac_fmt = ""
        scad_fmt = ""

        if pd.notna(lotto_raw) and str(lotto_raw).strip() != "":
            lotto_fmt = pd.to_datetime(lotto_raw).strftime("%d/%m/%y")

        if pd.notna(mac_raw) and str(mac_raw).strip() != "":
            mac_fmt = pd.to_datetime(mac_raw).strftime("%d/%m/%y")

        if pd.notna(scad_raw) and str(scad_raw).strip() != "":
            scad_fmt = pd.to_datetime(scad_raw).strftime("%d/%m/%y")

        descr = f"Pollo da Carne - Allevata in Italia e macellata presso la TuorloBiancofiore <br> Macello ITCE792V <br> - Lotto {mac_fmt}-{lotto_fmt} - Scad {scad_fmt} "

        # ===== CONTROLLO PREZZO SPECIALE =====

        prezzo_unit = None

        for _, sp in prezzi_speciali.iterrows():

            cliente_file = str(sp["Cliente"]).strip().lower()
            prodotto_file = str(sp["Prodotto"]).strip().lower()

            if cliente_file == nome.strip().lower() and prodotto_file in prod:
                prezzo_unit = float(sp["Prezzo"])
                break


# ===== SE NON TROVA PREZZO SPECIALE USA STANDARD =====

        if prezzo_unit is None:

            prezzo_match = prezzi[
        (prezzi["Prodotto"].str.lower().str.strip() == prod) &
        (prezzi["Paese"].str.lower().str.strip() == paese)
            ]

            prezzo_unit = float(prezzo_match.iloc[0]["Prezzo"]) if not prezzo_match.empty else 0

        prezzo_kg = prezzo_unit

        importo = prezzo_kg * kg
        
        sconto_percentuale = float(r.get("sconto_percentuale",0) or 0)
        sconto_importo = float(r.get("sconto_importo",0) or 0)

        if sconto_percentuale > 0:
            sconto_tot += importo * (sconto_percentuale / 100)

        if sconto_importo > 0:
            sconto_tot += sconto_importo

        importo_finale = importo - sconto_tot

        if importo_finale < 0:
            importo_finale = 0

        totale += importo
        
        if sconto_tot > 0:
            totale -= sconto_tot

        # riga prodotto → IMPORTO LORDO (senza sconto)
        prodotti_render.append({
            "qta": f"{round(kg,2)} kg",
            "descrizione": descr,
            "prezzo": "" if pagamento == "bonifico" else f"{importo:.2f}"
        })

        # riga sconto → solo se esiste
        if sconto_tot > 0:
            prodotti_render.append({
                "qta": "",
                "descrizione": "Sconto su ordine",
                "prezzo": f"-{sconto_tot:.2f}"
            })

        colli += 1
        continue


    # ================= PRODOTTI UOVA =================
    if any(x in prod for x in ["nobiluovo","novelle","l'ov","lov","180","carta","conf"]):

        if "nobiluovo" in prod:

            if "doppio" in prod:
                pezzi = 240
            elif "grande" in prod:
                pezzi = 120
            elif "piccolo" in prod:
                pezzi = 60
            else:
                pezzi = 120

        elif "novelle" in prod or "lov" in prod or "l'ov" in prod:

            if "grande" in prod:
                pezzi = 144
            elif "piccolo" in prod:
                pezzi = 72
            else:
                pezzi = 72

        elif "180" in prod:
            pezzi = 180

        elif "carta" in prod:
            pezzi = 30

        elif "conf" in prod:
            pezzi = 6

        else:
            pezzi = 0

        q_reale = pezzi * qta

        data_lotto_raw = r.get("Lotto", "")

        lotto_fmt = ""
        scad_fmt = ""

        if pd.notna(data_lotto_raw) and str(data_lotto_raw).strip() != "":
            data_lotto_dt = pd.to_datetime(data_lotto_raw)
            lotto_fmt = data_lotto_dt.strftime("%d/%m/%y")
            scad_fmt = (data_lotto_dt + timedelta(days=28)).strftime("%d/%m/%y")

        descr = f"Uova - Lotto {lotto_fmt} - Scad {scad_fmt}"


    # ================= OLIO =================
    elif "olio" in prod:

        if "cartone" in prod:

            pezzi = pezzi_per_cartone(prod)
            q_reale = pezzi * qta

        else:
            q_reale = qta

        descr = "Bottiglie 0.5L - Lot 10/2025 -- Scad 06/2027"


    # ================= TAGLIOLINI =================
    elif "tagliolini" in prod:

        pezzi = 12
        q_reale = pezzi * qta

        descr = "Pacchi di Tagliolini 500g - Lot 15525 -- Scad 05/2028"


    # ================= ORECCHIETTE =================
    elif "orecchiette" in prod:

        pezzi = 16
        q_reale = pezzi * qta

        descr = "Pacchi di Orecchiette 500g - Lot 15525 -- Scad 05/2028"


    # ================= SEMOLA =================
    elif "semola" in prod:
        if "cartone" in prod:

            pezzi = pezzi_per_cartone(prod)
            q_reale = pezzi * qta

        else:
            q_reale = qta
        descr = "Pacchi di Semola 1kg - Lot S170126 -- Scad 07/2026"


    # ===== CONTROLLO PREZZO SPECIALE =====

    prezzo_unit = None

    for _, sp in prezzi_speciali.iterrows():

        cliente_file = str(sp["Cliente"]).strip().lower()
        prodotto_file = str(sp["Prodotto"]).strip().lower()

        if cliente_file == nome.strip().lower() and prodotto_file in prod:
            prezzo_unit = float(sp["Prezzo"])
            break


    # ===== SE NON TROVA PREZZO SPECIALE USA PREZZO STANDARD =====

    if prezzo_unit is None:

        prezzo_match = prezzi[
            (prezzi["Prodotto"].str.lower().str.strip() == prod) &
            (prezzi["Paese"].str.lower().str.strip() == paese)
        ]

        prezzo_unit = float(prezzo_match.iloc[0]["Prezzo"]) if not prezzo_match.empty else 0


    # ===== CALCOLO IMPORTO =====

    importo = prezzo_unit * qta

    sconto_percentuale = float(r.get("sconto_percentuale",0) or 0)
    sconto_importo = float(r.get("sconto_importo",0) or 0)

    sconto_tot = 0

    if sconto_percentuale > 0:
        sconto_tot += importo * (sconto_percentuale / 100)

    if sconto_importo > 0:
        sconto_tot += sconto_importo

    importo_finale = importo - sconto_tot

    if importo_finale < 0:
        importo_finale = 0

    # aggiungo totale prodotto SENZA sconto
    totale += importo

    prodotti_render.append({
    "qta": q_reale,
    "descrizione": descr,
    "prezzo": "" if pagamento == "bonifico" else f"{importo:.2f}"
    })

# riga sconto separata
    if sconto_tot > 0:

        totale -= sconto_tot

        prodotti_render.append({
        "qta": "",
        "descrizione": "Sconto su ordine",
        "prezzo": f"-{sconto_tot:.2f}"
        })


    colli += 1

# ================= INSERIMENTO POLLO =================
for tipo, dati in pollo_raggruppati.items():

    descrizione = (
        f"Carne Avicola - Allevato in Italia e macellato presso la TuorloBiancofiore <br> Macello ITCE792V <br> - Lotto {dati['macellazione']}-{dati['lotto']} "
        f"- Scad {dati['scadenza']}"
    )

    prodotti_render.append({
        "qta": f"{round(dati['kg'],2)} kg",
        "descrizione": descrizione,
        "prezzo": "" if pagamento == "bonifico" else f"{round(dati['totale'],2):.2f}"
    })

    totale += dati["totale"]
    colli += 1

# ================= CALCOLO SOSPESO DINAMICO =================
sospesi_path = os.path.join(CONFIG, "sospesi.json")

if os.path.exists(sospesi_path):
    with open(sospesi_path) as f:
        sospesi = json.load(f)
else:
    sospesi = {}

sospeso_precedente = float(sospesi.get(telefono, {}).get("totale_sospeso", 0))

# 🔥 LOGICA CORRETTA
differenza = totale - pagato_oggi
sospeso_finale = sospeso_precedente + differenza

if sospeso_finale < 0:
    sospeso_finale = 0

saldato = sospeso_precedente > 0 and sospeso_finale == 0

print("TOTALE:", totale)
print("PAGATO:", pagato_oggi)
print("SOSPESO PRECEDENTE:", sospeso_precedente)
print("SOSPESO FINALE:", sospeso_finale)

# 🔥 SALVATAGGIO SOSPESO
sospesi[telefono] = {
    "totale_sospeso": round(sospeso_finale, 2),
    "scarichi": sospesi.get(telefono, {}).get("scarichi", [])
}

with open(sospesi_path, "w") as f:
    json.dump(sospesi, f, indent=4)
    
# ================= IMMAGINI =================
def file_uri(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")

timbro_path = os.path.join(CONFIG, "timbro.png")
firma_path = os.path.join(CONFIG, f"firma.png")

timbro = file_uri(timbro_path) if os.path.exists(timbro_path) else ""
firma = file_uri(firma_path) if os.path.exists(firma_path) else ""

# ================= TEMPLATE =================
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template = env.get_template("ddt_template.html")

html = template.render(
    numero=num_str,
    data=oggi,
    cliente=nome,
    indirizzo=indirizzo,
    citta=paese,
    prodotti=prodotti_render,
    totale="BONIFICO" if pagamento == "bonifico" else f"{totale:.2f}",
    colli=colli,
    timbro=timbro,
    firma=firma,
    firma_cliente="",
    sospeso=round(sospeso_finale, 2),
    mostra_sospeso=(sospeso_finale > 0),
    saldato=saldato
)

html_path = os.path.join(OUTPUT, f"ddt_{num_str}.html")

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

# PULIZIA NOME CLIENTE (importantissimo)
cliente_clean = nome.replace(" ", "_").replace("/", "").replace("\\", "")

pdf_path = os.path.join(
    OUTPUT,
    f"DDT_{num_str}_{cliente_clean}_{telefono}.pdf"
)

ultimo_file = os.path.join(CONFIG, f"ultimo_ddt_{telefono}.txt")
with open(ultimo_file, "w") as f:
    f.write(pdf_path)

pdfkit.from_file(
    html_path,
    pdf_path,
    configuration=config,
    options={
        "enable-local-file-access": None,
        "margin-top": "5mm",
        "margin-bottom": "5mm",
        "margin-left": "5mm",
        "margin-right": "5mm"
    }
)

numero += 1
with open(contatore, "w") as f:
    f.write(str(numero))

os.remove(html_path)

print("DDT CORRETTO CREATO")

# ===== AGGIORNA STATO ORDINI A CONSEGNATO =====

ordini_path = os.path.join(CONFIG, "ORDINI.xlsx")
ordini_df = pd.read_excel(ordini_path)

ordini_df["Telefono"] = ordini_df["Telefono"].astype(str)

mask = (ordini_df["Telefono"] == telefono) & (ordini_df["Stato"] == "nuovo")

ordini_df.loc[mask, "Stato"] = "consegnato"

ordini_df.to_excel(ordini_path, index=False)