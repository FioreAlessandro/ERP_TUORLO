import os
import sys
import json
from reportlab.pdfgen import canvas
from PyPDF2 import PdfReader, PdfWriter

telefono = sys.argv[1]

BASE = os.path.dirname(os.path.dirname(__file__))
CONFIG = os.path.join(BASE, "config")
OUTPUT = os.path.join(BASE, "output_pdf")

# ================= PRENDI DDT GIUSTO =================
file_info = os.path.join(CONFIG, f"ultimo_ddt_{telefono}.txt")

if not os.path.exists(file_info):
    print("DDT non trovato per questo cliente")
    sys.exit()

with open(file_info) as f:
    ddt_path = f.read().strip()

if not os.path.exists(ddt_path):
    print("File DDT inesistente")
    sys.exit()

# ================= FIRMA CLIENTE =================
firma_cliente = os.path.join(CONFIG, f"firma_{telefono}.png")

if not os.path.exists(firma_cliente):
    print("Firma cliente non trovata")
    sys.exit()

# ================= CREA OVERLAY =================
overlay_path = os.path.join(OUTPUT, f"overlay_{telefono}.pdf")

c = canvas.Canvas(overlay_path)

c.drawImage(
    firma_cliente,
    350,   # ← più a sinistra
    115,   # ← più in basso
    width=180,
    height=70,
    mask='auto'
)

c.save()

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

# ================= MERGE PDF =================
reader = PdfReader(ddt_path)
overlay = PdfReader(overlay_path)
writer = PdfWriter()

page = reader.pages[0]
page.merge_page(overlay.pages[0])
writer.add_page(page)

firmato = ddt_path.replace(".pdf","_firmato.pdf")

with open(firmato,"wb") as f:
    writer.write(f)

print("DDT firmato creato")

# ================= PULIZIA =================
os.remove(overlay_path)
os.remove(file_info)