# genera_ddt_finale.py
import json, os, sys
from jinja2 import Environment, FileSystemLoader
import pdfkit

telefono = sys.argv[1]

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")
OUTPUT = os.path.join(BASE, "output_pdf")
TEMPLATE_DIR = os.path.join(BASE, "script", "templates")

# legge sospeso aggiornato
sospesi_path = os.path.join(CONFIG, "sospesi.json")

if os.path.exists(sospesi_path):
    with open(sospesi_path) as f:
        sospesi = json.load(f)
else:
    sospesi = {}

cliente_sospeso = sospesi.get(telefono, {
    "totale_sospeso": 0,
    "scarichi": []
})

sospeso_attuale = float(cliente_sospeso.get("totale_sospeso", 0))

# prende ultimo DDT
file_info = os.path.join(CONFIG, f"ultimo_ddt_{telefono}.txt")

with open(file_info) as f:
    ddt_path = f.read().strip()

numero = os.path.basename(ddt_path).replace("DDT_","").replace(".pdf","")

# RICREA HTML con sospeso aggiornato
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
template = env.get_template("ddt_template.html")

html = template.render(
    sospeso=round(sospeso_attuale, 2),
    mostra_sospeso=(sospeso_attuale > 0)
)

html_path = os.path.join(OUTPUT, f"ddt_finale_{telefono}.html")

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

pdfkit.from_file(html_path, ddt_path)

os.remove(html_path)

print("DDT FINALE AGGIORNATO CON SOSPESO")