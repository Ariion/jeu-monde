"""
Compile le jeu en un seul exécutable Windows (.exe).

Usage:
    pip install pyinstaller
    python build.py
"""
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "JeuMonde",
    "--clean",
    "--distpath", os.path.join(HERE, "dist"),
    "--workpath", os.path.join(HERE, "build_tmp"),
    "--specpath", os.path.join(HERE, "build_tmp"),
    os.path.join(HERE, "main.py"),
]

print("Building JeuMonde.exe …")
result = subprocess.run(cmd, check=False)
if result.returncode == 0:
    print("\n✔  Succès ! L'exécutable est dans le dossier  dist/JeuMonde.exe")
else:
    print("\n✘  Erreur lors de la compilation.")
    sys.exit(1)
