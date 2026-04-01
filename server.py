
from flask import Flask, jsonify, render_template, request,redirect
import json
import os
import subprocess
import pandas as pd
import base64
import smtplib
from email.message import EmailMessage
import glob
from datetime import datetime, timedelta
import zipfile


BASE = os.path.dirname(os.path.dirname(__file__))
app = Flask(
    __name__,
    static_folder=os.path.join(BASE, "static"),
    static_url_path="/static"
)
# ===== PERCORSI =====

CONFIG = os.path.join(BASE, "config")
PDF = os.path.join(BASE, "output_pdf")
LISTA = os.path.join(CONFIG, "lista_consegne.json")
CODA_DDT = os.path.join(CONFIG, "coda_ddt.json")
DDT_TEMP = os.path.join(BASE, "DDT_TEMP")
os.makedirs(DDT_TEMP, exist_ok=True)

import sys
PYTHON = sys.executable

# ================= HOME =================
@app.route("/")
def home():
    if not os.path.exists(LISTA):
        return "Nessuna lista generata"
    return render_template("index.html")

@app.route("/menu_ddt")
def menu_ddt():
    return render_template("menu_ddt.html")

@app.route("/prepara_giro")
def prepara_giro():

    import shutil

    if not os.path.exists(LISTA):
        return jsonify({"errore":"Nessuna lista"})

    with open(LISTA) as f:
        lista = json.load(f)

    # 🔥 PULISCE TEMP PRIMA
    for f in os.listdir(DDT_TEMP):
        os.remove(os.path.join(DDT_TEMP, f))

    generati = []

    for c in lista:

        telefono = str(c["telefono"])

        print("📦 Genero DDT TEMP:", telefono)

        # 🔥 genera DDT NORMALE
        subprocess.run([
            PYTHON,
            os.path.join(BASE, "script", "genera_ddt_temp.py"),
            telefono,
            "temp"   # 🔥 FLAG
        ])

        # 🔥 prendi ultimo pdf generato
        files = glob.glob(os.path.join(DDT_TEMP, f"*{telefono}*.pdf"))

        if files:
            ultimo = max(files, key=os.path.getctime)
            generati.append(ultimo)

    if not generati:
        return jsonify({"errore":"Nessun DDT generato"})

    # ================= CREA ZIP =================

    oggi = datetime.now().strftime("%d_%m")
    nome_zip = f"giro_{oggi}.zip"
    zip_path = os.path.join(DDT_TEMP, nome_zip)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in generati:
            zipf.write(f, os.path.basename(f))

    return jsonify({
        "ok": True,
        "file": "/download_giro"
    })
    
    
from flask import send_file

@app.route("/download_giro")
def download_giro():

    files = os.listdir(DDT_TEMP)
    zip_files = [f for f in files if f.endswith(".zip")]

    if not zip_files:
        return "ZIP non trovato"

    ultimo = max(zip_files)

    path = os.path.join(DDT_TEMP, ultimo)

    return send_file(path, as_attachment=True)
    
@app.route("/genera_zip_gdo")
def genera_zip_gdo():

    import zipfile
    import subprocess
    from datetime import datetime

    tipo = request.args.get("tipo")  # "megamark" o "maiora"

    print("🔥 TIPO:", tipo)

    # ================= PULIZIA TEMP =================
    for f in os.listdir(DDT_TEMP):
        os.remove(os.path.join(DDT_TEMP, f))

    # ================= LEGGE ORDINI =================
    ordini_path = os.path.join(CONFIG, "ORDINI.xlsx")
    ordini_df = pd.read_excel(ordini_path)

    ordini_df["Telefono"] = ordini_df["Telefono"].astype(str)

    telefoni = []

    for _, r in ordini_df.iterrows():

        cliente = str(r.get("Cliente", "")).lower()

        if tipo == "megamark" and "mega" in cliente:
            telefoni.append(r["Telefono"])

        elif tipo == "maiora" and "maiora" in cliente:
            telefoni.append(r["Telefono"])

    telefoni = list(set(telefoni))

    print("📞 TELEFONI:", telefoni)

    if not telefoni:
        return jsonify({"errore": "Nessun cliente trovato"})

    # ================= SCELTA SCRIPT =================
    if tipo == "megamark":
        script = "genera_ddt_gdo_megamark.py"
    elif tipo == "maiora":
        script = "genera_ddt_gdo_maiora.py"
    else:
        return jsonify({"errore": "Tipo non valido"})

    # ================= GENERAZIONE DDT =================
    generati = []

    for telefono in telefoni:

        print("📦 Genero DDT:", telefono)

        subprocess.run([
            PYTHON,
            os.path.join(BASE, "script", script),
            telefono
        ])

    # ================= PRENDE PDF =================
    for f in os.listdir(DDT_TEMP):
        if f.endswith(".pdf"):
            generati.append(os.path.join(DDT_TEMP, f))

    print("📂 FILE GENERATI:", generati)

    if not generati:
        return jsonify({"errore": "Nessun DDT generato"})

    # ================= CREA ZIP =================
    oggi = datetime.now().strftime("%d_%m")
    nome_zip = f"gdo_{tipo}_{oggi}.zip"
    zip_path = os.path.join(DDT_TEMP, nome_zip)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in generati:
            zipf.write(f, os.path.basename(f))

    print("✅ ZIP CREATO:", nome_zip)
    print("contenuto temp: ", os.listdir(DDT_TEMP))

    return jsonify({
        "ok": True,
        "file": "/download_giro"
    })

# ================= API LISTA =================
@app.route("/api/lista")
def api_lista():
    if not os.path.exists(LISTA):
        return jsonify([])

    with open(LISTA) as f:
        data = json.load(f)

    return jsonify(data)


@app.route("/api/prodotti")
def api_prodotti():

    prezzi = pd.read_excel(os.path.join(CONFIG, "PREZZI.xlsx"))

    prodotti = (
        prezzi["Prodotto"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return jsonify(prodotti)

@app.route("/genera_lista", methods=["POST"])
def genera_lista():

    data_lotto = request.form.get("lotto")

    if not data_lotto:
        return jsonify({"errore": "Inserire data lotto"}), 400

    # salva lotto globale
    with open(os.path.join(CONFIG, "lotto.txt"), "w") as f:
        f.write(data_lotto)

    # 🔥 GENERA LISTA DIRETTAMENTE
    subprocess.run([
        PYTHON,
        os.path.join(BASE, "script", "genera_lista.py")
    ])

    print("🔥 LISTA GENERATA")

    return jsonify({"ok": True})
    

@app.route("/gestione_pollo")
def gestione_pollo():

    ordini = pd.read_excel(os.path.join(CONFIG, "ORDINI.xlsx"))
    clienti = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))

    ordini["Telefono"] = ordini["Telefono"].astype(str).str.strip()
    clienti["Telefono"] = clienti["Telefono"].astype(str).str.strip()
    ordini["Prodotto"] = ordini["Prodotto"].astype(str).str.lower().str.strip()

    # Considera solo ordini nuovi
    if "Stato" in ordini.columns:
        ordini = ordini[ordini["Stato"] == "nuovo"]

    tipi_prezzi = {
        "pollo allegretto": 7,
        "pollo maestoso": 9,
        "signor pollo": 12
    }

    clienti_pollo = []

    for _, r in ordini.iterrows():
        prod = r["Prodotto"]

        if prod in tipi_prezzi:

            tel = r["Telefono"]

            cliente_match = clienti[clienti["Telefono"] == tel]

            if cliente_match.empty:
                continue  # evita crash se cliente non trovato

            nome = cliente_match.iloc[0]["Nome"]

            clienti_pollo.append({
                "telefono": tel,
                "nome": nome,
                "tipo": prod,
                "prezzo_kg": tipi_prezzi[prod]
            })

    return render_template("gestione_pollo.html", clienti=clienti_pollo)

@app.route("/conferma_pollo", methods=["POST"])
def conferma_pollo():

    dati = request.json

    if not dati or "clienti" not in dati:
        return jsonify({"errore": "Dati mancanti"}), 400

    clienti = dati["clienti"]

    pollo_data = {}

    for c in clienti:

        telefono = c.get("telefono")
        tipo = c.get("tipo")
        prezzo_kg = float(c.get("prezzo_kg", 0))
        kg = float(c.get("kg", 0))
        macellazione = c.get("macellazione")
        lotto = c.get("lotto")

        # 🔴 VALIDAZIONE
        if not telefono or not tipo or not macellazione or not lotto or kg <= 0:
            return jsonify({"errore": "Dati pollo incompleti"}), 400

        data_mac = datetime.strptime(macellazione, "%Y-%m-%d")
        scadenza = (data_mac + timedelta(days=7)).strftime("%d/%m/%Y")

        prezzo_totale = round(kg * prezzo_kg, 2)

        if telefono not in pollo_data:
            pollo_data[telefono] = []

        pollo_data[telefono].append({
            "tipo": tipo,
            "kg": kg,
            "prezzo_totale": prezzo_totale,
            "macellazione": data_mac.strftime("%d/%m/%Y"),
            "lotto": datetime.strptime(lotto, "%Y-%m-%d").strftime("%d/%m/%Y"),
            "scadenza": scadenza
        })

    # 🔥 Salva struttura corretta
    with open(os.path.join(CONFIG, "pollo_temp.json"), "w") as f:
        json.dump(pollo_data, f, indent=4)

    # 🔥 Ora genera lista
    subprocess.run([
        PYTHON,
        os.path.join(BASE, "script", "genera_lista.py")
    ])

    return jsonify({"ok": True})
# ================= PAGINA CLIENTE =================
@app.route("/cliente/<telefono>")
def cliente(telefono):

    nofirma = request.args.get("nofirma","0")

    return render_template(
        "cliente.html",
        telefono=telefono,
        nofirma=nofirma
    )

@app.route("/generalista_senza_firma")
def generalista_senza_firma():
    return render_template("generalista.html", senza_firma=True)



# ================= ORDINI CLIENTE =================
@app.route("/api/ordini/<telefono>")
def api_ordini(telefono):

    ordini = pd.read_excel(os.path.join(CONFIG, "ORDINI.xlsx"))
    clienti = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))

    ordini["Telefono"] = ordini["Telefono"].astype(str)
    clienti["Telefono"] = clienti["Telefono"].astype(str)

    ord_cli = ordini[ordini["Telefono"] == telefono]

    if "Stato" in ord_cli.columns:
        ord_cli = ord_cli[ord_cli["Stato"] == "nuovo"]

    txt = []
    for _, r in ord_cli.iterrows():
        txt.append(f"{r['Prodotto']} x {r['Quantità']}")

    nome = clienti[clienti["Telefono"] == telefono].iloc[0]["Nome"]

    return jsonify({
        "nome": nome,
        "ordini": txt
    })


# ================= GENERA DDT =================
@app.route("/genera_ddt/<telefono>", methods=["POST"])
def genera_ddt(telefono):

    nofirma = request.args.get("nofirma") == "1"
    data = request.json
    pagato_oggi = float(data.get("pagato_oggi") or 0)

    pagamento_temp = os.path.join(CONFIG, f"pagamento_temp_{telefono}.json")

    # Se esiste già, lo leggiamo
    if os.path.exists(pagamento_temp):
        with open(pagamento_temp) as f:
            info = json.load(f)
    else:
        info = {}

    # Salviamo pagato_oggi
    info["pagato_oggi"] = pagato_oggi

    with open(pagamento_temp, "w") as f:
        json.dump(info, f, indent=4)

    subprocess.run([
        PYTHON,
        os.path.join(BASE, "script", "genera_ddt_pdf.py"),
        telefono
    ])
    
    if nofirma:
        subprocess.run([
        PYTHON,
        os.path.join(BASE, "script", "finalizza_ddt.py"),
        telefono
    ])
    
    
    # ================= SEGNA CLIENTE COME CONSEGNATO =================

    if os.path.exists(LISTA):
        with open(LISTA) as f:
            lista = json.load(f)

    for c in lista:
        if str(c["telefono"]) == telefono:
            c["stato"] = "consegnato"

    with open(LISTA, "w") as f:
        json.dump(lista, f, indent=4)

    print("🟢 Cliente segnato verde (DDT generato)")

    return "DDT generato"

@app.route("/api/dati_generalista_nofirma")
def dati_generalista_nofirma():

    clienti = pd.read_excel(os.path.join(CONFIG,"clienti_senza_firma.xlsx"))

    nomi = (
        clienti["Nome"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    prezzi = pd.read_excel(os.path.join(CONFIG,"PREZZI.xlsx"))

    prodotti = (
        prezzi["Prodotto"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return jsonify({
        "clienti": nomi,
        "prodotti": prodotti
    })

@app.route("/api/lista_nofirma")
def lista_nofirma():

    ordini = pd.read_excel(os.path.join(CONFIG,"ORDINI_NOFIRMA.xlsx"))

    clienti = []

    for nome in ordini["Nome"].unique():

        cli = carica_cliente(nome)

        clienti.append({
            "nome": nome,
            "telefono": cli["Telefono"]
        })

    return jsonify(clienti)

@app.route("/invia_ddt_clienti", methods=["POST"])
def invia_ddt_clienti():

    clienti = pd.read_excel(os.path.join(CONFIG,"clienti_senza_firma.xlsx"))

    for _, c in clienti.iterrows():

        email = str(c.get("Email","")).strip()

        if email == "" or email.lower()=="nan":
            continue

        telefono = str(c["Telefono"])

        file_ddt = os.path.join(CONFIG,f"ultimo_ddt_{telefono}.txt")

        if not os.path.exists(file_ddt):
            continue

        with open(file_ddt) as f:
            pdf = f.read().strip()

        msg = EmailMessage()

        msg["Subject"] = "DDT consegna"
        msg["From"] = "consegne.tuorlobiancofiore@gmail.com"
        msg["To"] = email

        msg.set_content("In allegato il DDT della consegna.")

        with open(pdf,"rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(pdf)
            )

        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:

            smtp.login(
                "consegne.tuorlobiancofiore@gmail.com",
                "uisi wkyd icbo mhth"
            )

            smtp.send_message(msg)

    return "DDT inviati"

# ================= PAGINA FIRMA =================
@app.route("/firma/<telefono>")
def firma(telefono):

    index = request.args.get("index")
    tipo = request.args.get("tipo")

    print("📞 FIRMA TELEFONO:", telefono)
    print("📦 INDEX:", index)
    print("📦 TIPO:", tipo)

    # 🔥 FLUSSO GDO / MAIORA / UOVA SFUSE
    if (
        telefono.startswith("gdo_") 
        or telefono.startswith("maiora_")
        or telefono.startswith("uova_sfuse_")
    ):
        return render_template(
            "firma.html",
            telefono=telefono,
            index=index,
            tipo=tipo
        )

    # 🔥 FLUSSO CLIENTI NORMALI
    else:
        return render_template(
            "firma.html",
            telefono=telefono,
            index=-1,
            tipo="normale"
        )

@app.route("/salva_firma", methods=["POST"])
def salva_firma():
    import json
    import subprocess
    print("Entrato")
    try:
        data = request.json
        telefono = str(data["telefono"])
        index=int(data.get("index", -1))
        firma_base64 = data["firma"]

        # ================= SALVA FIRMA =================
        for file in os.listdir(CONFIG):
            if file.startswith(f"firma_{telefono}"):
                os.remove(os.path.join(CONFIG, file))

        firma_base64 = firma_base64.split(",")[1]
        imgdata = base64.b64decode(firma_base64)

        firma_path = os.path.join(CONFIG, f"firma_{telefono}.png")
        with open(firma_path, "wb") as f:
            f.write(imgdata)

        print("✔ Firma cliente salvata")
        
        # ================= GENERAZIONE DDT =================
        tipo = data.get("tipo") or "gdo"
        print("🔥 TIPO RICEVUTO:", tipo)

# ================= UOVA SFUSE (SEMPRE FUORI) =================
        if tipo == "uova_sfuse":

            path = os.path.join(CONFIG, "coda_uova_sfuse.json")

            if not os.path.exists(path):
                print("❌ FILE UOVA SFUSE NON TROVATO")
            else:
                with open(path) as f:
                    lista = json.load(f)

                if 0 <= index < len(lista):

                    ordine = lista[index]

                    ordine["telefono"] = telefono

                    print("📦 ORDINE UOVA SFUSE:", ordine)

                    subprocess.run([
                        PYTHON,
                        os.path.join(BASE, "script", "genera_ddt_uova_sfuse.py"),
                        json.dumps(ordine)
                    ])

                    lista[index]["stato"] = "completato"

                    with open(path, "w") as f:
                        json.dump(lista, f, indent=2)

                    print("✅ UOVA SFUSE COMPLETATO")

                else:
                    print("❌ INDEX NON VALIDO UOVA SFUSE:", index)

# ================= GDO / MAIORA =================
        elif os.path.exists(CODA_DDT):

            with open(CODA_DDT) as f:
                lista = json.load(f)

            if 0 <= index < len(lista):

                d = lista[index]
                tipo_ddt = d.get("tipo", "gdo")

                print("🔥 GENERO DDT:", tipo_ddt)

                d["telefono"] = telefono

                if tipo_ddt == "maiora":
                    subprocess.run([
                        PYTHON,
                        os.path.join(BASE, "script", "genera_ddt_maiora.py"),
                        json.dumps(d)
                    ])
                else:
                    subprocess.run([
                        PYTHON,
                        os.path.join(BASE, "script", "genera_ddt_gdo.py"),
                        json.dumps(d)
                    ])

                print("✅ DDT GENERATO")
                # 🔥 SEGNA COME COMPLETATO SUBITO
                lista[index]["stato"] = "completato"

                with open(CODA_DDT, "w") as f:
                    json.dump(lista, f, indent=4)

                print("🟢 COMPLETATO SUBITO:", index)
                # ================= RIGENERA PDF FIRMATO =================
        subprocess.run([
            PYTHON,
            os.path.join(BASE, "script", "finalizza_ddt.py"),
            telefono
        ])

        # ================= TROVA PDF FIRMATO =================
        import glob

# cerca il pdf firmato più recente di quel cliente
        files = glob.glob(os.path.join(PDF, f"*{telefono}*_firmato.pdf"))

        if not files:
            print("⚠️ PDF firmato non trovato")
            ddt_file = None
        else:
            ddt_file = max(files, key=os.path.getctime)

        print("✔ PDF firmato trovato:", ddt_file)

        # ================= INVIO MAIL CLIENTE =================
        if tipo == "maiora":
            file_clienti = "clienti_maiora.xlsx"
            col_tel = "Telefono" if "Telefono" in pd.read_excel(os.path.join(CONFIG, file_clienti)).columns else None
        else:
            file_clienti = "CLIENTI.xlsx"
            col_tel = "Telefono"

        clienti = pd.read_excel(os.path.join(CONFIG, file_clienti))
        clienti.columns = clienti.columns.str.strip()

        if col_tel:
            clienti[col_tel] = clienti[col_tel].astype(str).str.strip()
        
        clienti.columns=clienti.columns.str.strip()
        
        clienti["Telefono"] = clienti["Telefono"].astype(str).str.strip()

        cliente = clienti[clienti["Telefono"] == telefono]
        print("📍 TELEFONO:", telefono)
        print("📍 CLIENTE TROVATO:", not cliente.empty)

        if not cliente.empty:
            print("📍 RIGA CLIENTE:", cliente.iloc[0].to_dict())
        email_cliente=""
        if not cliente.empty:
            email_cliente = str(cliente.iloc[0]["Email"]).strip().lower()
            print("EMAIL: ", email_cliente)

            if email_cliente and "@" in email_cliente:

                mittente = "consegne.tuorlobiancofiore@gmail.com"
                password = "uisi wkyd icbo mhth"

                msg = EmailMessage()
                data_mail = datetime.now().strftime("%d/%m/%Y")

                msg["Subject"] = f"DDT Consegna {data_mail}"
                msg["From"] = mittente
                msg["To"] = email_cliente
                msg.set_content(
                    "Gentile cliente,\n\n"
                    "In allegato trova il DDT firmato della consegna.\n\n"
                    "Cordiali saluti\n"
                    "Tuorlo BiancoFiore"
                )
                if ddt_file:
                    with open(ddt_file, "rb") as f:
                        msg.add_attachment(
                        f.read(),
                        maintype="application",
                        subtype="pdf",
                        filename=os.path.basename(ddt_file)
                        )

                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                        smtp.login(mittente, password)
                        smtp.send_message(msg)

                    print("📧 Mail cliente inviata con successo")
        print("📞 TELEFONO ARRIVATO:", telefono)

        with open(CODA_DDT) as f:
            lista = json.load(f)

        for d in lista:
            print("📦 IN CODA:", d.get("telefono"))
        if "@" not in email_cliente:
            print("❌ EMAIL NON VALIDA:", email_cliente)
            return jsonify({"errore":"email non valida"})
        if os.path.exists(CODA_DDT):

            with open(CODA_DDT) as f:
                lista = json.load(f)

            trovato = False

            if 0 <= index < len(lista):

                lista[index]["stato"] = "completato"

                print("🟢 COMPLETATO INDEX:", index)

            else:
                print("❌ INDEX NON VALIDO:", index)

            if not trovato:
                print("❌ NON TROVATO TELEFONO:", telefono)

            with open(CODA_DDT, "w") as f:
                json.dump(lista, f, indent=4)

            print("🟢 GDO aggiornato completato")

        # ================= RECUPERA DATI TEMP =================
        pagamento_temp = os.path.join(CONFIG, f"pagamento_temp_{telefono}.json")

        if not os.path.exists(pagamento_temp):
            return "ERRORE PAGAMENTO TEMP", 500

        with open(pagamento_temp) as f:
            info = json.load(f)

        totale_attuale = float(info.get("totale_attuale", 0))
        pagato_oggi = float(info.get("pagato_oggi", 0))

        # ================= AGGIORNAMENTO SOSPESO DEFINITIVO =================
        sospesi_path = os.path.join(CONFIG, "sospesi.json")

        if os.path.exists(sospesi_path):
            with open(sospesi_path) as f:
                sospesi = json.load(f)
        else:
            sospesi = {}

        sospeso_precedente = float(
            sospesi.get(telefono, {}).get("totale_sospeso", 0)
        )

        nuovo_sospeso = sospeso_precedente + totale_attuale - pagato_oggi

        if nuovo_sospeso < 0:
            nuovo_sospeso = 0

        sospesi[telefono] = {
            "totale_sospeso": round(nuovo_sospeso, 2),
            "scarichi": sospesi.get(telefono, {}).get("scarichi", [])
        }

        with open(sospesi_path, "w") as f:
            json.dump(sospesi, f, indent=4)

        print("NUOVO SOSPESO:", round(nuovo_sospeso, 2))

        os.remove(pagamento_temp)

        return jsonify({"ok": True})

    except Exception as e:
        print("ERRORE SALVA FIRMA:", e)
        return "errore", 500
    
@app.route("/generalista")
def generalista():
    return render_template(
        "generalista.html",
        
    )

@app.route("/genera_ddt_uova_sfuse", methods=["POST"])
def salva_dati_uova_sfuse():

    data = request.json
    path = os.path.join(CONFIG, "coda_uova_sfuse.json")

    with open(path) as f:
        lista = json.load(f)

    index = int(data["id"])

    # 🔥 SALVA DATI COMPLETI
    lista[index]["lotti"] = data.get("lotti", [])
    lista[index]["pedane"] = data.get("pedane", [])

    with open(path, "w") as f:
        json.dump(lista, f, indent=2)

    print("✅ DATI SALVATI:", lista[index])

    return jsonify({"ok": True})

@app.route("/api/dati_generalista")
def dati_generalista():

    clienti_df = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
    prezzi_df = pd.read_excel(os.path.join(CONFIG, "PREZZI.xlsx"))
    
    clienti = (
        clienti_df["Nome"]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    prodotti = (
        prezzi_df["Prodotto"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return jsonify({
        "clienti": clienti,
        "prodotti": prodotti
    })
    
@app.route("/fine_giornata_uova_sfuse")
def fine_giornata_uova_sfuse():

    import zipfile
    from datetime import datetime

    mittente = "consegne.tuorlobiancofiore@gmail.com"
    password = "uisi wkyd icbo mhth"

    base_dir = os.path.join(BASE, "RIEPILOGO_DDT")

    anno = datetime.now().strftime("%Y")
    mese = datetime.now().strftime("%m")

    mesi = [
        "gennaio","febbraio","marzo","aprile","maggio","giugno",
        "luglio","agosto","settembre","ottobre","novembre","dicembre"
    ]

    mese_nome = mesi[int(mese)-1]

    cartella = os.path.join(
        base_dir,
        f"{anno}_UOVA_SFUSE",
        f"{mese}_{mese_nome}"
    )

    if not os.path.exists(cartella):
        return "Nessun DDT"

    files = [
        os.path.join(cartella, f)
        for f in os.listdir(cartella)
        if f.endswith(".pdf")
    ]

    if not files:
        return "Nessun PDF"

    # ================= CREA ZIP =================
    zip_path = os.path.join(BASE, "riepilogo_uova_sfuse.zip")

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in files:
            zipf.write(f, os.path.basename(f))

    # ================= INVIO MAIL =================
    msg = EmailMessage()
    msg["Subject"] = "Riepilogo Uova Sfuse"
    msg["From"] = mittente
    msg["To"] = mittente

    msg.set_content(f"Totale DDT generati: {len(files)}")

    with open(zip_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="zip",
            filename="uova_sfuse.zip"
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mittente, password)
        smtp.send_message(msg)

    print("📧 Mail riepilogo inviata")

    # ================= 🔥 SVUOTA SOLO LA CODA =================
    path = os.path.join(CONFIG, "coda_uova_sfuse.json")

    if os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f, indent=2)

        print("🧹 LISTA UOVA SFUSE AZZERATA")

    # ❌ NON tocchiamo i PDF
    # ❌ NON tocchiamo archivio

    # ================= ELIMINA ZIP TEMP =================
    if os.path.exists(zip_path):
        os.remove(zip_path)

    return "Fine giornata completata 🚀"
    
@app.route("/generalista_nofirma")
def generalista_nofirma():
    return render_template("generalista_nofirma.html")



@app.route("/api/cliente_info/<telefono>")
def cliente_info_ddt(telefono):

    clienti = pd.read_excel(os.path.join(CONFIG,"CLIENTI.xlsx"))
    ordini = pd.read_excel(os.path.join(CONFIG,"ORDINI.xlsx"))

    clienti.columns = clienti.columns.str.strip()
    ordini.columns = ordini.columns.str.strip()

    clienti["Telefono"] = clienti["Telefono"].astype(str).str.strip()
    ordini["Telefono"] = ordini["Telefono"].astype(str).str.strip()

    c = clienti[clienti["Telefono"] == str(telefono)]

    if c.empty:
        return jsonify({"ddt": False, "stato": "in_attesa"})

    c = c.iloc[0]

    # ===== CONTROLLO DDT ROBUSTO =====
    valore_ddt = str(c.get("ddt","")).strip().lower()
    valore_firma = str(c.get("firma","")).strip().lower()

    ddt_attivo = valore_ddt in [
        "si","sì","1","true","ok","x"
    ]

    firma_richiesta = not (valore_firma == "no")

    # ===== STATO CONSEGNA =====
    stato = "in_attesa"

    ord_cli = ordini[ordini["Telefono"] == str(telefono)]

    if "Stato" in ord_cli.columns:
        if not ord_cli.empty and all(ord_cli["Stato"].astype(str) == "consegnato"):
            stato = "consegnato"
    pagamento=str(c.get("Pagamento","")).strip()
    return jsonify({
        "ddt": True,
        "stato": stato,
        "pagamento":pagamento
    })

@app.route("/api/sospeso/<telefono>")
def api_sospeso(telefono):

    sospesi_path = os.path.join(CONFIG, "sospesi.json")

    sospesi = {}
    totale_attuale = 0

    # ===== LEGGE SOSPESI =====
    if os.path.exists(sospesi_path):
        try:
            with open(sospesi_path, "r") as f:
                contenuto = f.read().strip()
                if contenuto:
                    sospesi = json.loads(contenuto)
        except Exception as e:
            print("ERRORE LETTURA SOSPESI:", e)

    cliente_sospeso = sospesi.get(
        telefono,
        {
            "totale_sospeso": 0,
            "scarichi": []
        }
    )

    # ===== CARICA FILE =====
    ordini_path = os.path.join(CONFIG, "ORDINI.xlsx")
    clienti_path = os.path.join(CONFIG, "CLIENTI.xlsx")
    prezzi_path = os.path.join(CONFIG, "PREZZI.xlsx")
    prezzi_speciali_path = os.path.join(CONFIG, "PREZZI_SPECIALI.xlsx")

    ordini = pd.read_excel(ordini_path)
    clienti = pd.read_excel(clienti_path)
    prezzi = pd.read_excel(prezzi_path)
    prezzi_speciali = pd.read_excel(prezzi_speciali_path)

    ordini["Telefono"] = ordini["Telefono"].astype(str)
    clienti["Telefono"] = clienti["Telefono"].astype(str)

    # ===== ORDINI CLIENTE =====
    ord_cli = ordini[ordini["Telefono"] == telefono]

    if "Stato" in ord_cli.columns:
        ord_cli = ord_cli[ord_cli["Stato"] == "nuovo"]

    if not ord_cli.empty:

        cliente_match = clienti[clienti["Telefono"] == telefono]

        if not cliente_match.empty:
            paese = str(cliente_match.iloc[0]["Paese"]).lower().strip()
            cliente_nome = str(cliente_match.iloc[0]["Nome"]).lower().strip()
        else:
            paese = ""
            cliente_nome = ""

        prezzi["Prodotto"] = prezzi["Prodotto"].astype(str).str.lower().str.strip()
        prezzi["Paese"] = prezzi["Paese"].astype(str).str.lower().str.strip()

        for _, r in ord_cli.iterrows():

            prod = str(r["Prodotto"]).lower().strip()
            qta = int(r["Quantità"])

            # ===== PREZZO SPECIALE =====
            prezzo = None

            for _, sp in prezzi_speciali.iterrows():

                cliente_file = str(sp["Cliente"]).strip().lower()
                prodotto_file = str(sp["Prodotto"]).strip().lower()

                if cliente_file == cliente_nome and prodotto_file in prod:
                    prezzo = float(sp["Prezzo"])
                    break


            # ===== PREZZO STANDARD =====
            if prezzo is None:

                prezzo_match = prezzi[
                    (prezzi["Prodotto"] == prod) &
                    (prezzi["Paese"] == paese)
                ]

                prezzo = float(prezzo_match.iloc[0]["Prezzo"]) if not prezzo_match.empty else 0


            # ===== IMPORTO =====
            if "pollo" in prod:

                kg = float(r.get("Kg", 0))
                importo = prezzo * kg

            else:

                importo = prezzo * qta


            # ===== SCONTI =====
            sconto_percentuale = float(r.get("sconto_percentuale", 0) or 0)
            sconto_importo = float(r.get("sconto_importo", 0) or 0)

            sconto_tot = 0

            if sconto_percentuale > 0:
                sconto_tot += importo * (sconto_percentuale / 100)

            if sconto_importo > 0:
                sconto_tot += sconto_importo

            importo_finale = importo - sconto_tot

            if importo_finale < 0:
                importo_finale = 0

            totale_attuale += importo_finale


    return jsonify({
        "totale_sospeso": cliente_sospeso.get("totale_sospeso", 0),
        "scarichi": cliente_sospeso.get("scarichi", []),
        "totale_ordine": round(totale_attuale, 2)
    })
    
@app.route("/spedizioni")
def spedizioni():
    return render_template("spedizioni.html")

@app.route("/api/clienti_sped")
def clienti_sped():

    file_path = os.path.join(CONFIG,"CLIENTI_SPED.xlsx")

    df = pd.read_excel(file_path)

    clienti = df["Cliente"].dropna().tolist()

    return jsonify(clienti)

@app.route("/genera_ddt_sped", methods=["POST"])
def genera_ddt_sped():

    data=request.json

    cliente=data["cliente"]
    prodotti=data["prodotti"]

    sconto_percentuale=float(data.get("sconto_percentuale",0) or 0)
    sconto_importo=float(data.get("sconto_importo",0) or 0)

    script=os.path.join(BASE,"script","genera_ddt_spedizione.py")

    subprocess.run([
        "python",
        script,
        json.dumps({
            "cliente":cliente,
            "prodotti":prodotti,
            "sconto_percentuale":sconto_percentuale,
            "sconto_importo":sconto_importo
        })
    ])

    return jsonify({"ok":True})
    
@app.route("/salva_ordini", methods=["POST"])
def salva_ordini():

    nuovi_ordini = request.json

    clienti_df = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
    ordini_df = pd.read_excel(os.path.join(CONFIG, "ORDINI.xlsx"))
    # 🔒 sicurezza colonne sconto
    for col in [
    "usa_sconto",
    "tipo_sconto",
    "sconto_percentuale",
    "sconto_importo",
    "prodotto_sconto"
    ]:
        if col not in ordini_df.columns:
            ordini_df[col] = ""

    clienti_df["Nome"] = clienti_df["Nome"].astype(str).str.strip()
    clienti_df["Telefono"] = clienti_df["Telefono"].astype(str).str.strip()

    nuove_righe = []

    from datetime import datetime, timedelta

    for o in nuovi_ordini:

        cliente_nome = str(o.get("cliente","")).strip()
        prodotto = str(o.get("prodotto","")).strip()

        cliente_row = clienti_df[
            clienti_df["Nome"] == cliente_nome
        ]

        if cliente_row.empty:
            continue

        telefono = str(cliente_row.iloc[0]["Telefono"]).strip()

        lotto = o.get("lotto","")
        macellazione = o.get("macellazione","")
        kg = o.get("kg","")

        scadenza = ""

        # 🔥 SCADENZA AUTOMATICA POLLO
        if "pollo" in prodotto.lower() and macellazione:

            data_mac = datetime.strptime(macellazione,"%Y-%m-%d")
            scadenza = (data_mac + timedelta(days=7)).strftime("%Y-%m-%d")

        nuova_riga = {
    "Telefono": telefono,
    "Prodotto": prodotto,
    "Quantità": o.get("quantita",1),
    "Lotto": lotto,
    "Macellazione": macellazione,
    "Scadenza": scadenza,
    "Kg": kg,

    # 🔴 CAMPI SCONTO
    "usa_sconto": o.get("usa_sconto","no"),
    "tipo_sconto": o.get("tipo_sconto",""),
    "sconto_percentuale": o.get("sconto_percentuale",0),
    "sconto_importo": o.get("sconto_importo",0),
    "prodotto_sconto": o.get("prodotto_sconto",""),

    "Stato": "nuovo"
}

        nuove_righe.append(nuova_riga)

    if nuove_righe:

        ordini_df = pd.concat(
            [ordini_df, pd.DataFrame(nuove_righe)],
            ignore_index=True
        )

        ordini_df.to_excel(
            os.path.join(CONFIG,"ORDINI.xlsx"),
            index=False
        )

    return jsonify({"ok": True})

@app.route("/salva_ordini_nofirma", methods=["POST"])
def salva_ordini_nofirma():

    nuovi_ordini = request.json

    clienti_df = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
    ordini_path = os.path.join(CONFIG, "ORDINI_NOFIRMA.xlsx")

    if os.path.exists(ordini_path):
         ordini_df = pd.read_excel(ordini_path)
    else:
        ordini_df = pd.DataFrame()
    # 🔒 sicurezza colonne sconto
    for col in [
    "usa_sconto",
    "tipo_sconto",
    "sconto_percentuale",
    "sconto_importo",
    "prodotto_sconto"
    ]:
        if col not in ordini_df.columns:
            ordini_df[col] = ""

    clienti_df["Nome"] = clienti_df["Nome"].astype(str).str.strip()
    clienti_df["Telefono"] = clienti_df["Telefono"].astype(str).str.strip()

    nuove_righe = []

    from datetime import datetime, timedelta

    for o in nuovi_ordini:

        cliente_nome = str(o.get("cliente","")).strip()
        prodotto = str(o.get("prodotto","")).strip()

        cliente_row = clienti_df[
            clienti_df["Nome"] == cliente_nome
        ]

        if cliente_row.empty:
            continue

        telefono = str(cliente_row.iloc[0]["Telefono"]).strip()

        lotto = o.get("lotto","")
        macellazione = o.get("macellazione","")
        kg = o.get("kg","")

        scadenza = ""

        # 🔥 SCADENZA AUTOMATICA POLLO
        if "pollo" in prodotto.lower() and macellazione:

            data_mac = datetime.strptime(macellazione,"%Y-%m-%d")
            scadenza = (data_mac + timedelta(days=7)).strftime("%Y-%m-%d")

        nuova_riga = {
    "Telefono": telefono,
    "Prodotto": prodotto,
    "Quantità": o.get("quantita",1),
    "Lotto": lotto,
    "Macellazione": macellazione,
    "Scadenza": scadenza,
    "Kg": kg,

    # 🔴 CAMPI SCONTO
    "usa_sconto": o.get("usa_sconto","no"),
    "tipo_sconto": o.get("tipo_sconto",""),
    "sconto_percentuale": o.get("sconto_percentuale",0),
    "sconto_importo": o.get("sconto_importo",0),
    "prodotto_sconto": o.get("prodotto_sconto",""),

    "Stato": "nuovo"
}

        nuove_righe.append(nuova_riga)

    if nuove_righe:

        ordini_df = pd.concat(
            [ordini_df, pd.DataFrame(nuove_righe)],
            ignore_index=True
        )

        ordini_df.to_excel(
            ordini_path,
            index=False
        )

    return jsonify({"ok": True})

@app.route("/gdo_menu")
def gdo_menu():
    return render_template("gdo_menu.html")

@app.route("/gdo_megamark")
def gdo_megamark():
    return render_template("gdo.html")

@app.route("/gdo_maiora")
def gdo_maiora():
    return render_template("gdo_maiora.html")

@app.route("/api/clienti_maiora")
def clienti_maiora():

    df = pd.read_excel(os.path.join(CONFIG, "clienti_maiora.xlsx"))

    clienti = []

    for _, r in df.iterrows():
        clienti.append({
            "nome": str(r["Nome"]).strip(),
            "sede": str(r["Sede"]).strip(),
            "citta": str(r["Citta"]).strip(),
            "piva": str(r["Piva"]).strip()
        })

    return jsonify(clienti)

@app.route("/genera_ddt_maiora", methods=["POST"])
def genera_ddt_maiora():

    data = request.json

    subprocess.run([
        PYTHON,
        os.path.join(BASE,"genera_ddt_maiora.py"),
        json.dumps(data)
    ])

    return jsonify({"ok":True})

@app.route("/fine_giornata_gdo")
def fine_giornata_gdo():

    import os
    import zipfile
    import smtplib
    from email.message import EmailMessage
    from datetime import datetime

    mittente = "consegne.tuorlobiancofiore@gmail.com"
    password = "uisi wkyd icbo mhth"

    # ================= DATA =================
    oggi = datetime.now()
    oggi_date = oggi.date()

    anno = oggi.strftime("%Y")
    mese_num = oggi.strftime("%m")

    mesi = [
    "gennaio","febbraio","marzo","aprile","maggio","giugno",
    "luglio","agosto","settembre","ottobre","novembre","dicembre"
    ]

    mese_nome = mesi[int(mese_num)-1]
    cartella_mese = f"{mese_num}_{mese_nome}"

    # ================= CARTELLA CORRETTA =================
    cartelle = [
    os.path.join(BASE, "RIEPILOGO_DDT", f"{anno}_GDO", cartella_mese),
    os.path.join(BASE, "RIEPILOGO_DDT", f"{anno}_MAIORA", cartella_mese)
    ]

    files = []

    # 🔥 controllo esistenza cartella
    files = []

    for base in cartelle:

        if not os.path.exists(base):
            continue

    for file in os.listdir(base):

        if not file.endswith(".pdf"):
            continue

        path_file = os.path.join(base, file)

        data_file = datetime.fromtimestamp(
            os.path.getmtime(path_file)
        ).date()

        if data_file == oggi_date:
            files.append(path_file)

    if not files:
        return "Nessun DDT GDO oggi"

    # ================= CREA ZIP =================
    zip_path = os.path.join(BASE, "gdo_riepilogo.zip")

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in files:
            zipf.write(f, os.path.basename(f))

    # ================= EMAIL =================
    msg = EmailMessage()
    msg["Subject"] = "Riepilogo DDT GDO"
    msg["From"] = mittente
    msg["To"] = mittente

    msg.set_content(f"Totale DDT GDO oggi: {len(files)}")

    with open(zip_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="zip",
            filename="DDT_GDO.zip"
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mittente, password)
        smtp.send_message(msg)

    print("📧 Riepilogo GDO inviato")

    # ================= PULIZIA CODA =================
    with open(CODA_DDT, "w") as f:
        json.dump([], f)
        print("🧹 CODA GDO AZZERATA")

    # opzionale: elimina zip
    if os.path.exists(zip_path):
        os.remove(zip_path)
# ================= PULIZIA TOTALE OUTPUT_PDF =================

    output_pdf_dir = os.path.join(BASE, "output_pdf")

    if os.path.exists(output_pdf_dir):

        for nome in os.listdir(output_pdf_dir):

            path = os.path.join(output_pdf_dir, nome)

            try:
                if os.path.isfile(path):
                    os.remove(path)

                elif os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path)

            except Exception as e:
                print("❌ Errore eliminazione:", path, e)

    print("🧹 OUTPUT_PDF COMPLETAMENTE SVUOTATA")
    
    return jsonify({"ok": True})

@app.route("/genera_ddt_multipli", methods=["POST"])
def genera_ddt_multipli():

    lista = request.json

    risultati = []

    for d in lista:
        try:
            # 👉 lancia script maiora
            subprocess.run([
                "python",
                "script/genera_ddt_maiora.py",
                json.dumps(d)
            ], check=True)

            risultati.append({
                "cliente": d["cliente"],
                "status": "ok"
            })

        except Exception as e:
            risultati.append({
                "cliente": d["cliente"],
                "status": "errore",
                "errore": str(e)
            })

    return jsonify({
        "risultati": risultati   # 🔥 FONDAMENTALE
    })

@app.route("/aggiungi_multipli_maiora", methods=["POST"])
def aggiungi_multipli_maiora():

    nuovi = request.json

    if os.path.exists(CODA_DDT):
        with open(CODA_DDT) as f:
            lista = json.load(f)
    else:
        lista = []

    for i, d in enumerate(nuovi):

        d["tipo"] = "maiora"
        d["stato"] = "pending"              # 🔥 FONDAMENTALE
        d["id"] = len(lista) + i            # 🔥 coerente
        d["telefono"] = f"maiora_{len(lista)+i}"  # 🔥 FONDAMENTALE

        lista.append(d)

    with open(CODA_DDT, "w") as f:
        json.dump(lista, f)

    return jsonify({"ok": True})

@app.route("/giri")
def giri():

    if not os.path.exists(CODA_DDT):
        return render_template("giri.html", lista=[])

    try:
        with open(CODA_DDT) as f:
            contenuto = f.read().strip()

            if not contenuto:
                lista = []
            else:
                lista = json.loads(contenuto)

    except Exception as e:
        print("ERRORE LETTURA CODA:", e)
        lista = []

    return render_template("giri.html", lista=lista)

@app.route("/dettaglio/<int:index>")
def dettaglio(index):

    with open(CODA_DDT) as f:
        lista = json.load(f)

    d = lista[index]

    return render_template(
        "dettaglio.html",
        cliente=d["cliente"],
        pedane=d["pedane"],
        telefono=d["telefono"],
        index=index,
        tipo=d.get("tipo", "gdo")
    )
    
@app.route("/genera_da_coda/<int:i>", methods=["POST"])
def genera_da_coda(i):

    with open(CODA_DDT) as f:
        lista = json.load(f)

    d = lista[i]
    # 🔥 assegna telefono univoco per firma
    d["telefono"] = f"{d.get('tipo','gdo')}_{i}"

    # 🔥 salva dati temporanei per la firma
    temp_path = os.path.join(CONFIG, f"gdo_temp_{d['telefono']}.json")

    with open(temp_path, "w") as f:
        json.dump(d, f, indent=4)

    return {"ok": True}

@app.route("/genera_ddt_nofirma/<telefono>", methods=["POST"])
def genera_ddt_nofirma(telefono):

    subprocess.run([
        PYTHON,
        os.path.join(BASE, "script", "genera_ddt_pdf.py"),
        telefono
    ])

    return "DDT generato"

@app.route("/fine_giornata")
def fine_giornata():
    

    try:

        mittente = "consegne.tuorlobiancofiore@gmail.com"
        password = "uisi wkyd icbo mhth"

        lista_pdf = glob.glob(os.path.join(PDF, "*_firmato.pdf"))

        if not lista_pdf:
            return "Nessun DDT oggi"

        msg = EmailMessage()
        data_mail = datetime.now().strftime("%d/%m/%Y")

        msg["Subject"] = f"Riepilogo DDT {data_mail}"
        msg["From"] = mittente
        msg["To"] = mittente
        msg.set_content(
            f"Riepilogo DDT firmati.\n\nTotale DDT: {len(lista_pdf)}"
        )   

        zip_path = os.path.join(PDF, "riepilogo_ddt.zip")

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in lista_pdf:
                zipf.write(file, os.path.basename(file))

        with open(zip_path, "rb") as f:
            msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="zip",
            filename="DDT_giornata.zip"
                )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:

            smtp.login(mittente, password)
            smtp.send_message(msg)

        print("📧 Riepilogo inviato")



        # ================= ARCHIVIO DDT =================

        riepilogo_ddt = os.path.join(BASE, "RIEPILOGO_DDT")

        anno = datetime.now().strftime("%Y")
        mese = datetime.now().strftime("%m")
        nome_mese = datetime.now().strftime("%B")

        cartella_mese = f"{mese}_{nome_mese}"

        dest_dir = os.path.join(riepilogo_ddt, anno, cartella_mese)

        os.makedirs(dest_dir, exist_ok=True)

        clienti_df = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
        clienti_df["Telefono"] = clienti_df["Telefono"].astype(str)


        for file in lista_pdf:

            src = file
            nome = os.path.splitext(os.path.basename(file))[0]

            # rimuove "_firmato"
            nome = nome.replace("_firmato", "")

            parti = nome.split("_")

            numero_ddt = "000"
            telefono = ""

            if len(parti) >= 3:
                numero_ddt = parti[1]
                telefono = parti[-1]

            cliente_match = clienti_df[clienti_df["Telefono"] == str(telefono)]

            if not cliente_match.empty:
                nome_cliente = cliente_match.iloc[0]["Nome"].replace(" ", "")
            else:
                nome_cliente = "Cliente"

            data_file = datetime.now().strftime("%Y-%m-%d")

            nuovo_nome = f"DDT_{numero_ddt}_{data_file}_{nome_cliente}.pdf"

            dest = os.path.join(dest_dir, nuovo_nome)

            import shutil
            shutil.move(src, dest)

        print("📦 DDT firmati archiviati in:", dest_dir)



        # ================= CANCELLA DDT NON FIRMATI =================

        for file in os.listdir(PDF):

            if file.endswith(".pdf"):
                os.remove(os.path.join(PDF, file))

        print("🧹 PDF temporanei eliminati")



        # ================= PULISCI FIRME CLIENTI =================

        firme = glob.glob(os.path.join(CONFIG, "firma_*.png"))

        for f in firme:
            os.remove(f)

        print("🧹 Firme clienti cancellate")

        # 🔥 PULISCI DDT TEMP
        if os.path.exists(DDT_TEMP):
            for f in os.listdir(DDT_TEMP):
                os.remove(os.path.join(DDT_TEMP, f))

            print("🧹 DDT TEMP PULITI")

        # ================= ELIMINA LISTA =================

        if os.path.exists(LISTA):
            os.remove(LISTA)



# ================= ARCHIVIO ORDINI =================

        ordini_path = os.path.join(CONFIG, "ORDINI.xlsx")
        clienti_path = os.path.join(CONFIG, "CLIENTI.xlsx")
        prezzi_path = os.path.join(CONFIG, "PREZZI.xlsx")
        prezzi_speciali = pd.read_excel(os.path.join(CONFIG,"PREZZI_SPECIALI.xlsx"))

        totale_incasso = 0

        if os.path.exists(ordini_path):

            ordini_df = pd.read_excel(ordini_path)
            clienti_df = pd.read_excel(clienti_path)
            prezzi_df = pd.read_excel(prezzi_path)

            ordini_df["Telefono"] = ordini_df["Telefono"].astype(str)
            clienti_df["Telefono"] = clienti_df["Telefono"].astype(str)

            prezzi_df["Prodotto"] = prezzi_df["Prodotto"].astype(str).str.lower().str.strip()
            prezzi_df["Paese"] = prezzi_df["Paese"].astype(str).str.lower().str.strip()

            righe = []

            for _, r in ordini_df.iterrows():

                tel = str(r["Telefono"])
                prodotto = str(r["Prodotto"]).lower().strip()
                quantita = float(r["Quantità"])

                cliente_match = clienti_df[clienti_df["Telefono"] == tel]

                if not cliente_match.empty:
                    nome_cliente = str(cliente_match.iloc[0]["Nome"]).lower().strip()
                    pagamento = cliente_match.iloc[0]["Pagamento"]
                    paese = str(cliente_match.iloc[0]["Paese"]).lower().strip()
                else:
                    nome_cliente = tel
                    pagamento = ""
                    paese = ""

        # ===== PREZZO SPECIALE =====
                prezzo = None

                for _, sp in prezzi_speciali.iterrows():

                    cliente_file = str(sp["Cliente"]).strip().lower()
                    prodotto_file = str(sp["Prodotto"]).strip().lower()

                    if cliente_file == nome_cliente and prodotto_file in prodotto:
                        prezzo = float(sp["Prezzo"])
                        break


        # ===== PREZZO STANDARD =====
                if prezzo is None:

                    prezzo_match = prezzi_df[
                (prezzi_df["Prodotto"] == prodotto) &
                (prezzi_df["Paese"] == paese)
                    ]

                    prezzo = float(prezzo_match.iloc[0]["Prezzo"]) if not prezzo_match.empty else 0


        # ===== IMPORTO BASE =====
                kg = 0

                if "pollo" in prodotto:
                    kg = float(r.get("Kg", 0))
                    importo = kg * prezzo
                else:
                    importo = prezzo * quantita


        # ===== APPLICA SCONTI =====
                sconto_percentuale = float(r.get("sconto_percentuale",0) or 0)
                sconto_importo = float(r.get("sconto_importo",0) or 0)

                if sconto_percentuale > 0:
                    importo -= importo * (sconto_percentuale / 100)

                if sconto_importo > 0:
                    importo -= sconto_importo

                if importo < 0:
                    importo = 0

                totale_incasso += importo

                righe.append({
            "Paese": paese,
            "Cliente": nome_cliente,
            "Prodotto": prodotto,
            "Quantità": quantita,
            "Pagamento": pagamento,
            "Kg": kg,
            "Totale": round(importo,2)
                })


            df = pd.DataFrame(righe)

            if not df.empty:

                df = df.sort_values(["Paese","Cliente"])

                output = []

                data_oggi = datetime.now().strftime("%d/%m/%Y")

                output.append({
            "Cliente": f"RIEPILOGO ORDINI DEL {data_oggi}"
                })

                output.append({})

                prima_citta = True

                for paese, gruppo_paese in df.groupby("Paese"):

                    if not prima_citta:
                        output.append({})

                    output.append({"Cliente": paese.upper()})

                    ultimo_cliente = None

                    for _, r in gruppo_paese.iterrows():

                        cliente_nome = r["Cliente"] if r["Cliente"] != ultimo_cliente else ""

                        prodotto = str(r["Prodotto"]).lower()

                        quantita = r["Quantità"]
                        totale_riga = r["Totale"]

                        if "pollo" in prodotto:
                            kg = float(r.get("Kg",0))
                            quantita = f"{kg} Kg"

                        output.append({
                    "Cliente": cliente_nome,
                    "Prodotto": r["Prodotto"],
                    "Quantità": quantita,
                    "Pagamento": r["Pagamento"],
                    "Totale": totale_riga
                        })

                        ultimo_cliente = r["Cliente"]
                        prima_citta = False


                output.append({})
                output.append({
            "Cliente": "TOTALE INCASSO GIORNATA",
            "Totale": round(totale_incasso,2)
                })
                # ================= RIEPILOGO SOSPESI =================

                sospesi_path = os.path.join(CONFIG, "sospesi.json")

                if os.path.exists(sospesi_path):

                    with open(sospesi_path) as f:
                        sospesi = json.load(f)

                    clienti_df = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
                    clienti_df["Telefono"] = clienti_df["Telefono"].astype(str)

                    output.append({})
                    output.append({})
                    output.append({"Cliente": "RIEPILOGO SOSPESI"})

                    for telefono, dati in sospesi.items():

                        totale = float(dati.get("totale_sospeso", 0))

        # 🔥 SALTA ZERO
                        if totale <= 0:
                            continue

                        cliente_match = clienti_df[
                            clienti_df["Telefono"] == str(telefono)
                        ]

                        if not cliente_match.empty:
                            nome_cliente = cliente_match.iloc[0]["Nome"]
                        else:
                            nome_cliente = telefono

                        output.append({
                            "Cliente": nome_cliente,
                            "Totale": round(totale, 2)
                        })

                archivio_df = pd.DataFrame(output)

                archivio_dir = os.path.join(CONFIG, "archivio_ordini")
                os.makedirs(archivio_dir, exist_ok=True)

                data_file = datetime.now().strftime("%Y_%m_%d")

                archivio_file = os.path.join(
            archivio_dir,
            f"ordini_{data_file}.xlsx"
                )

                archivio_df.to_excel(archivio_file, index=False, header=False)

                print("📦 ORDINI ARCHIVIATI:", archivio_file)



        # ================= PULISCI ORDINI =================

                if os.path.exists(ordini_path):

                    ordini_df = pd.read_excel(ordini_path)
                    ordini_df = ordini_df.iloc[0:0]
                    ordini_df.to_excel(ordini_path, index=False)

                    print("🧹 ORDINI PULITI")



                print(f"💰 INCASSO TOTALE: {round(totale_incasso,2)} €")

                return "Fine giornata completata"

    except Exception as e:

        print("ERRORE FINE GIORNATA:", e)
        return "Errore fine giornata"

@app.route("/api/mancate_consegne")
def mancate_consegne():

    ordini_path = os.path.join(CONFIG,"ORDINI.xlsx")
    clienti_path = os.path.join(CONFIG,"CLIENTI.xlsx")

    if not os.path.exists(ordini_path):
        return jsonify([])

    ordini = pd.read_excel(ordini_path)
    clienti = pd.read_excel(clienti_path)

    ordini["Telefono"] = ordini["Telefono"].astype(str)
    clienti["Telefono"] = clienti["Telefono"].astype(str)

    lista = []

    for _, r in ordini.iterrows():

        tel = str(r["Telefono"])

        cliente = clienti[clienti["Telefono"] == tel]

        if cliente.empty:
            continue

        stato = r.get("Stato","attesa")

        if stato != "consegnato":

            lista.append({
                "telefono": tel,
                "nome": cliente.iloc[0]["Nome"],
                "paese": cliente.iloc[0]["Paese"]
            })

    return jsonify(lista)

@app.route("/uova_sfuse")
def uova_sfuse():

    clienti = pd.read_excel(os.path.join(CONFIG, "CLIENTI_UOVA_SFUSE.xlsx"))
    nomi = clienti["Nome"].dropna().tolist()

    return render_template("uova_sfuse.html", clienti=nomi)

@app.route("/salva_uova_sfuse", methods=["POST"])
def salva_uova_sfuse():

    data = request.json

    path = os.path.join(CONFIG, "coda_uova_sfuse.json")

    if os.path.exists(path):
        with open(path) as f:
            lista = json.load(f)
    else:
        lista = []

    data["id"] = len(lista)
    data["telefono"] = f"uova_sfuse_{data['id']}"
    data["stato"] = "pending"

    lista.append(data)

    with open(path, "w") as f:
        json.dump(lista, f, indent=2)

    print("✅ ORDINE SALVATO:", data)

    return "ok"

@app.route("/uova_sfuse_lista")
def uova_sfuse_lista():

    path = os.path.join(CONFIG, "coda_uova_sfuse.json")

    if not os.path.exists(path):
        lista = []
    else:
        with open(path) as f:
            lista = json.load(f)

    return render_template("lista_uova_sfuse.html", lista=lista)

UOVA_TEMP = os.path.join(CONFIG, "uova_sfuse_temp.json")
@app.route("/uova_sfuse_dettaglio")
def dettaglio_uova_sfuse():

    id_param = request.args.get("id")

    path = os.path.join(CONFIG, "coda_uova_sfuse.json")

    if not os.path.exists(path):
        return "❌ Nessun ordine"

    with open(path) as f:
        lista = json.load(f)

    # 🔥 SE NON PASSI ID → PRENDE IL PRIMO
    if id_param is None:
        ordine = lista[0]
        id = 0
    else:
        id = int(id_param)
        ordine = lista[id]

    return render_template(
        "dettaglio_uova_sfuse.html",
        ordine=ordine,
        id=id
    )

@app.route("/gdo")
def gdo():
    return render_template("gdo.html")

@app.route("/salva_mancate", methods=["POST"])
def salva_mancate():

    data = request.json
    mancati = data["clienti"]

    file = os.path.join(CONFIG,"STORICO_CONSEGNE.xlsx")

    if os.path.exists(file):
        df = pd.read_excel(file)
    else:
        df = pd.DataFrame(columns=[
            "Data",
            "Cliente",
            "Telefono",
            "Paese",
            "Consegnato",
            "Motivo"
        ])

    for c in mancati:

        df.loc[len(df)] = {
"Data": datetime.now().strftime("%d/%m/%Y"),
"Cliente": c["nome"],
"Telefono": c["telefono"],
"Paese": c["paese"],
"Consegnato": "NO",
"Motivo": c["motivo"]
}

    df.to_excel(file,index=False)

    return "ok"

@app.route("/nuovo")
def nuovo():
    return render_template("nuovo.html")

@app.route("/nuovo_prodotto")
def nuovo_prodotto():
    return render_template("nuovo_prodotto.html")

@app.route("/salva_prodotto", methods=["POST"])
def salva_prodotto():

    data = request.json

    file = os.path.join(CONFIG,"PREZZI.xlsx")

    df = pd.read_excel(file)

    nuovo = pd.DataFrame([{
        "Prodotto": data["nome"],
        "Paese": data["paese"],
        "Prezzo": float(data["prezzo"])
    }])

    df = pd.concat([df, nuovo], ignore_index=True)

    df.to_excel(file,index=False)

    return "ok"
   
@app.route("/nuovo_cliente")
def nuovo_cliente():
    return render_template("nuovo_cliente.html")

@app.route("/salva_cliente", methods=["POST"])
def salva_cliente():

    try:

        data = request.json

        nome = str(data.get("nome","")).strip()
        telefono = str(data.get("telefono","")).strip()
        indirizzo = str(data.get("indirizzo","")).strip()
        citta = str(data.get("citta","")).strip()
        pagamento = str(data.get("pagamento","")).strip()
        email = str(data.get("email","")).strip()
        tipo = str(data.get("tipo","")).strip()

        # ===============================
        # CONTROLLI DATI
        # ===============================

        if nome == "":
            return {"errore":"Nome cliente mancante"}

        if telefono == "":
            return {"errore":"Telefono mancante"}

        if not telefono.isdigit():
            return {"errore":"Telefono non valido"}

        # ===============================
        # SCEGLIE FILE
        # ===============================

        if tipo == "locale":
            file = os.path.join(CONFIG,"CLIENTI.xlsx")
        else:
            file = os.path.join(CONFIG,"clienti_sped.xlsx")

        if not os.path.exists(file):
            return {"errore":"File clienti non trovato"}

        df = pd.read_excel(file)

        # ===============================
        # CONTROLLO TELEFONO DUPLICATO
        # ===============================

        tel_col = None

        for c in df.columns:
            if "telefon" in c.lower():
                tel_col = c
                break

        if tel_col:

            if telefono in df[tel_col].astype(str).values:
                return {"errore":"Cliente già esistente"}

        # ===============================
        # TROVA COLONNA ID
        # ===============================

        id_col = None

        for c in df.columns:
            if "id" in c.lower():
                id_col = c
                break

        if id_col is None:
            id_col = df.columns[0]

        if df.empty:
            nuovo_id = 1
        else:
            nuovo_id = int(df[id_col].max()) + 1

        # ===============================
        # CREA NUOVA RIGA
        # ===============================

        nuova_riga = {}

        for col in df.columns:

            nome_col = col.lower()

            if "id" in nome_col:
                nuova_riga[col] = nuovo_id

            elif "nome" in nome_col or "cliente" in nome_col:
                nuova_riga[col] = nome

            elif "telefon" in nome_col:
                nuova_riga[col] = telefono

            elif "indirizzo" in nome_col:
                nuova_riga[col] = indirizzo

            elif "citt" in nome_col or "paese" in nome_col:
                nuova_riga[col] = citta

            elif "pagamento" in nome_col:
                nuova_riga[col] = pagamento
            
            elif "email" in nome_col:
                nuova_riga[col] = email

            elif "ddt" in nome_col:
                nuova_riga[col] = "SI"

            elif "attivo" in nome_col:
                nuova_riga[col] = "SI"

            else:
                nuova_riga[col] = ""

        # ===============================
        # SALVA
        # ===============================

        df = pd.concat([df, pd.DataFrame([nuova_riga])], ignore_index=True)

        df.to_excel(file, index=False)

        print("✅ Cliente salvato:", nome)

        return {"success":"Cliente salvato"}

    except Exception as e:

        print("ERRORE SALVA CLIENTE:", e)

        return {"errore":"Errore salvataggio cliente"}
    
@app.route("/modifica")
def modifica():
    return render_template("modifica.html")

@app.route("/modifica_cliente")
def modifica_cliente():
    return render_template("modifica_cliente.html")


@app.route("/modifica_prodotto")
def modifica_prodotto():
    return render_template("modifica_prodotto.html") 

@app.route("/salva_modifica_cliente", methods=["POST"])
def salva_modifica_cliente():

    data = request.json

    telefono_originale = str(data["telefono_originale"])
    telefono_nuovo = str(data["Telefono"])

    file_clienti = os.path.join(CONFIG,"CLIENTI.xlsx")
    file_sped = os.path.join(CONFIG,"clienti_sped.xlsx")

    # ===== TROVA IL FILE CORRETTO =====

    df = pd.read_excel(file_clienti)
    df["Telefono"] = df["Telefono"].astype(str)

    if telefono_originale in df["Telefono"].values:

        file = file_clienti

    else:

        df = pd.read_excel(file_sped)
        df["Telefono"] = df["Telefono"].astype(str)

        if telefono_originale in df["Telefono"].values:

            file = file_sped

        else:

            return {"errore":"Cliente non trovato"}

    # ===== RICARICA FILE =====

    df = pd.read_excel(file)
    df["Telefono"] = df["Telefono"].astype(str)

    for col in data:

        if col == "telefono_originale":
            continue

        valore = data[col]

        if valore == "":
            valore = None

        # fix clienti sped
        if col == "Nome" and "Cliente" in df.columns:
            col = "Cliente"

        if col not in df.columns:
            continue

        try:

            if pd.api.types.is_integer_dtype(df[col]):
                if valore is not None:
                    valore = int(valore)

            elif pd.api.types.is_float_dtype(df[col]):
                if valore is not None:
                    valore = float(valore)

        except:
            pass

        df.loc[df["Telefono"] == telefono_originale, col] = valore

    # aggiorna telefono se modificato
    df.loc[df["Telefono"] == telefono_originale, "Telefono"] = telefono_nuovo

    df.to_excel(file,index=False)

    return "ok"

@app.route("/salva_modifica_prodotto", methods=["POST"])
def salva_modifica_prodotto():

    data = request.json
    idx = int(data["id"])

    file = os.path.join(CONFIG,"PREZZI.xlsx")

    df = pd.read_excel(file)

    for col in data:

        if col != "id" and col in df.columns:

            valore = data[col]

            # se è vuoto
            if valore == "":
                valore = None

            # prova conversione numero
            try:
                if df[col].dtype == "float64":
                    valore = float(valore)
                elif df[col].dtype == "int64":
                    valore = int(valore)
            except:
                pass

            df.loc[idx,col] = valore

    df.to_excel(file,index=False)

    return "ok"

@app.route("/elimina_cliente", methods=["POST"])
def elimina_cliente():

    data = request.json

    telefono = str(data["telefono"])
    tipo = data["tipo"]

    if tipo == "locale":

        file = os.path.join(CONFIG,"CLIENTI.xlsx")
        df = pd.read_excel(file)

        df = df[df["Telefono"].astype(str) != telefono]

        df.to_excel(file,index=False)

    else:

        file = os.path.join(CONFIG,"clienti_sped.xlsx")
        df = pd.read_excel(file)

        df = df[df["Telefono"].astype(str) != telefono]

        df.to_excel(file,index=False)

    return "ok"

@app.route("/elimina_prodotto", methods=["POST"])
def elimina_prodotto():

    data = request.json
    idx = int(data["id"])

    file = os.path.join(CONFIG,"PREZZI.xlsx")

    df = pd.read_excel(file)

    df = df.drop(idx).reset_index(drop=True)

    df.to_excel(file,index=False)

    return "ok"


@app.route("/api_prodotto_info")
def api_prodotto_info():

    idx = int(request.args.get("id"))

    file = os.path.join(CONFIG,"PREZZI.xlsx")

    df = pd.read_excel(file)

    r = df.iloc[idx]

    dati = {}

    for col in df.columns:
        dati[col] = "" if pd.isna(r[col]) else r[col]

    return jsonify(dati)

@app.route("/api/cliente_info")
def cliente_info():

    telefono = request.args.get("telefono")
    tipo = request.args.get("tipo")

    if tipo == "locale":
        file = os.path.join(CONFIG,"CLIENTI.xlsx")
    else:
        file = os.path.join(CONFIG,"clienti_sped.xlsx")

    df = pd.read_excel(file)

    riga = df[df["Telefono"].astype(str)==telefono]

    if riga.empty:
        return {}

    dati = riga.iloc[0].to_dict()

    # FIX JSON
    for k in dati:
        if pd.isna(dati[k]):
            dati[k] = ""
        else:
            dati[k] = str(dati[k])

    return jsonify(dati)

@app.route("/gestione")
def gestione():
    return render_template("gestione.html")


@app.route("/rimuovi")
def rimuovi():
    return render_template("rimuovi.html")

@app.route("/rimuovi_cliente")
def rimuovi_cliente():
    return render_template("rimuovi_cliente.html")


@app.route("/rimuovi_prodotto")
def rimuovi_prodotto():
    return render_template("rimuovi_prodotto.html")

@app.route("/api_lista_clienti")
def api_lista_clienti():

    file_locali = os.path.join(CONFIG,"CLIENTI.xlsx")
    file_sped = os.path.join(CONFIG,"clienti_sped.xlsx")

    df_locali = pd.read_excel(file_locali)
    df_sped = pd.read_excel(file_sped)

    clienti = []

    for _, r in df_locali.iterrows():

        clienti.append({
            "nome": r["Nome"],
            "telefono": str(r["Telefono"]),
            "tipo": "locale"
        })

    for _, r in df_sped.iterrows():

        clienti.append({
            "nome": r["Cliente"],
            "telefono": str(r["Telefono"]),
            "tipo": "spedizione"
        })

    return jsonify(clienti)

@app.route("/api_lista_prodotti")
def api_lista_prodotti():

    file = os.path.join(CONFIG,"PREZZI.xlsx")

    df = pd.read_excel(file)

    prodotti = []

    for i, r in df.iterrows():

        if pd.isna(r["Prodotto"]):
            continue

        prodotti.append({
            "id": int(i),
            "nome": str(r["Prodotto"]),
            "paese": str(r["Paese"])
        })

    return jsonify(prodotti)

@app.route("/salva_spedizione", methods=["POST"])
def salva_spedizione():

    data = request.json

    file = os.path.join(CONFIG,"spedizioni_temp.json")

    if os.path.exists(file):

        with open(file) as f:
            lista=json.load(f)

    else:

        lista=[]

    lista.append(data)

    with open(file,"w") as f:
        json.dump(lista,f,indent=4)

    return "ok"

@app.route("/genera_ddt_spedizioni")
def genera_ddt_spedizioni():

    file = os.path.join(CONFIG,"spedizioni_temp.json")

    if not os.path.exists(file):
        return jsonify({"errore":"Nessuna spedizione"})

    with open(file) as f:
        spedizioni=json.load(f)

    pdf_generati=[]

    for s in spedizioni:

        subprocess.run([
            PYTHON,
            os.path.join(BASE,"script","genera_ddt_spedizione.py"),
            json.dumps(s)
        ])

    os.remove(file)

    return jsonify({"ok":True})
   
# ================= ULTIMO NUMERO DDT =================
@app.route("/api/ultimo_ddt")
def api_ultimo_ddt():

    contatore = os.path.join(CONFIG, "contatore_ddt.txt")

    if not os.path.exists(contatore):
        print("❌ Contatore non trovato")
        return jsonify({"numero": "---"})

    try:
        with open(contatore) as f:
            numero_raw = f.read().strip()

        print("VALORE CONTATORE RAW:", numero_raw)

        if numero_raw.isdigit():
            numero = int(numero_raw) - 1
            if numero < 0:
                numero = 0

            numero = str(numero).zfill(3)

            print("NUMERO CALCOLATO:", numero)

            return jsonify({"numero": numero})

        else:
            print("❌ Contatore non numerico")
            return jsonify({"numero": "---"})

    except Exception as e:
        print("ERRORE LETTURA CONTATORE:", e)
        return jsonify({"numero": "---"})
    
@app.route("/api/dashboard_live")
def dashboard_live():

    import json
    import pandas as pd
    import os

    ordini_path = os.path.join(CONFIG, "ORDINI.xlsx")
    sospesi_file = os.path.join(CONFIG, "sospesi.json")
    contatore = os.path.join(CONFIG, "contatore_ddt.txt")

    consegnati = 0
    nuovi = 0
    totale_clienti = 0
    totale_sospesi = 0
    ultimo_ddt = "---"

    if os.path.exists(ordini_path):

        ordini = pd.read_excel(ordini_path)

        ordini["Telefono"] = ordini["Telefono"].astype(str)

        if "Stato" in ordini.columns:

            consegnati = len(
                ordini[ordini["Stato"] == "consegnato"]["Telefono"].unique()
            )

            nuovi = len(
                ordini[ordini["Stato"] == "nuovo"]["Telefono"].unique()
            )

        totale_clienti = len(ordini["Telefono"].unique())

    # ===== ULTIMO DDT =====

    if os.path.exists(contatore):

        with open(contatore) as f:
            num = f.read().strip()

        if num.isdigit():
            ultimo_ddt = str(int(num) - 1).zfill(3)

    # ===== SOSPESI =====

    if os.path.exists(sospesi_file):

        with open(sospesi_file) as f:
            sospesi = json.load(f)

        for c in sospesi.values():
            totale_sospesi += float(c.get("totale_sospeso", 0))

    return jsonify({
        "ddt": ultimo_ddt,
        "consegnati": consegnati,
        "in_attesa": nuovi,
        "totale_clienti": totale_clienti,
        "sospesi": round(totale_sospesi, 2)
    })
    
@app.route("/api/prezzo_prodotto")
def prezzo_prodotto():

    prodotto = request.args.get("prodotto","").strip().lower()
    cliente = request.args.get("cliente","").strip().lower()

    # ===== PREZZO STANDARD =====
    df_prezzi = pd.read_excel("../config/PREZZI.xlsx")

    prezzo_base = 0

    for _, r in df_prezzi.iterrows():

        prod_excel = str(r["Prodotto"]).strip().lower()

        if prod_excel in prodotto:
            prezzo_base = float(r["Prezzo"])
            break


    # ===== PREZZI SPECIALI =====
    try:

        df_speciali = pd.read_excel("../config/PREZZI_SPECIALI.xlsx")

        for _, r in df_speciali.iterrows():

            cliente_file = str(r["Cliente"]).strip().lower()
            prodotto_file = str(r["Prodotto"]).strip().lower()

            if cliente == cliente_file and prodotto_file in prodotto:

                return jsonify({
                    "prezzo": float(r["Prezzo"])
                })

    except Exception as e:
        print("Errore prezzi speciali:", e)


    return jsonify({
        "prezzo": prezzo_base
    })


@app.route("/api_spedizioni_temp")
def api_spedizioni_temp():

    file = os.path.join(CONFIG,"spedizioni_temp.json")

    if not os.path.exists(file):
        return jsonify([])

    with open(file) as f:
        data=json.load(f)

    return jsonify(data)


@app.route("/api/clienti_gdo")
def api_clienti_gdo():

    BASE = os.path.dirname(os.path.dirname(__file__))
    CONFIG = os.path.join(BASE,"config")

    file_clienti = os.path.join(CONFIG,"CLIENTI_GDO.xlsx")

    df = pd.read_excel(file_clienti)

    clienti = df.iloc[:,0].dropna().astype(str).tolist()

    return jsonify(clienti)

@app.route("/api/cliente_gdo/<nome>")
def cliente_gdo(nome):

    df = pd.read_excel("config/CLIENTI_GDO.xlsx")

    r = df[df["RagioneSociale"] == nome].iloc[0]

    return jsonify({
        "via": r["Via"],
        "citta": r["Citta"],
        "piva": r["PIVA"],
        "consegna_via": r["Consegna_Via"],
        "consegna_citta": r["Consegna_Citta"],
        "email": r["Email"]
    })
    
@app.route("/genera_ddt_gdo",methods=["POST"])
def genera_ddt_gdo():

    data = request.json

    # ===== SALVA IN CODA =====
    if os.path.exists(CODA_DDT):
        with open(CODA_DDT) as f:
            coda = json.load(f)
    else:
        coda = []

    data["stato"] = "pending"
    data["id"] = len(coda)
    data["telefono"] = "gdo_" + str(len(coda))   # 🔥 AGGIUNGI QUESTA RIGA

    coda.append(data)

    with open(CODA_DDT,"w") as f:
        json.dump(coda,f,indent=4)

    return jsonify({
        "ok":True,
        "redirect":"/giri"
    })
    
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# ================= AVVIO SERVER =================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)