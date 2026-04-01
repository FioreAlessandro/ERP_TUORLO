import pandas as pd
import os
import json

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")

clienti = pd.read_excel(os.path.join(CONFIG, "CLIENTI.xlsx"))
ordini = pd.read_excel(os.path.join(CONFIG, "ORDINI.xlsx"))

clienti["Telefono"] = clienti["Telefono"].astype(str).str.strip()
ordini["Telefono"] = ordini["Telefono"].astype(str).str.strip()

lista = []

for telefono in ordini["Telefono"].unique():

    ord_cli = ordini[ordini["Telefono"] == telefono]

    if "Stato" in ord_cli.columns:
        ord_cli = ord_cli[ord_cli["Stato"] == "nuovo"]

    if ord_cli.empty:
        continue

    cliente = clienti[clienti["Telefono"] == telefono]

    if cliente.empty:
        continue

    c = cliente.iloc[0]

    # -------- CONTROLLO DDT --------
    ddt_raw = str(c.get("DDT", "")).strip().upper()
    ddt_attivo = True if ddt_raw in ["SI", "SÌ", "YES", "1"] else False

    lista.append({
        "telefono": telefono,
        "nome": c["Nome"],
        "paese": c["Paese"],
        "stato": "in_attesa",
        "ddt": ddt_attivo
    })

out = os.path.join(CONFIG, "lista_consegne.json")

with open(out, "w", encoding="utf-8") as f:
    json.dump(lista, f, indent=4)

print("LISTA CREATA OK")