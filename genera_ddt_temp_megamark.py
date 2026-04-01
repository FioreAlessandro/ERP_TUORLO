# genera_ddt_gdo_megamark.py
import subprocess, sys, os

telefono = sys.argv[1]
BASE = os.path.dirname(os.path.dirname(__file__))

subprocess.run([
    sys.executable,
    os.path.join(BASE, "script", "genera_ddt_temp.py"),
    telefono,
    "temp"
])