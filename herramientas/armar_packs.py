#!/usr/bin/env python3
"""
armar_packs.py - Arma los resource packs de Java de FUNKY PUNKY MC desde las carpetas del repo.

Cada carpeta de packs/ con pack.mcmeta y assets/ es un pack independiente que ForcePack manda
a los jugadores (Minecraft 1.20.3+ acepta varios packs a la vez):

    packs/base/       TAB, panel de AuthMe, panorama y ruleta HD  -> salida/FunkyPunky-Base.zip
    packs/mascotas/   modelos de BetterModel                      -> salida/FunkyPunky-Mascotas.zip
    packs/armaduras/  (cuando exista)                             -> salida/FunkyPunky-Armaduras.zip

Pasos:
  1. Genera las piezas de cada mascotas/*.bbmodel dentro de packs/mascotas/ (bb2bettermodel.py).
     Los .bbmodel de mascotas/servidor/ NO se regeneran (sus piezas las hizo el servidor).
  2. Revisa que todo JSON se pueda leer y que cada modelo y textura que se usa exista.
  3. Comprime cada pack de forma determinista (mismo contenido = mismo zip = misma SHA-1).
  4. Escribe salida/SHA1.txt.

Uso (desde cualquier carpeta):
    python3 -I herramientas/armar_packs.py
Si algo falla, sale con error y no escribe los zips (así nunca se publica un pack roto).
"""
import hashlib
import json
import os
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = os.path.join(RAIZ, "packs")
SALIDA = os.path.join(RAIZ, "salida")
MASCOTAS = os.path.join(RAIZ, "mascotas")
GENERADOR = os.path.join(RAIZ, "herramientas", "bb2bettermodel.py")
LIMITE_BYTES = 250 * 1024 * 1024        # máximo que acepta Java 1.18+
FECHA_FIJA = (2026, 1, 1, 0, 0, 0)      # fecha fija dentro del zip -> SHA-1 estable


def generar_mascotas():
    modelos = sorted(
        os.path.join(MASCOTAS, f) for f in os.listdir(MASCOTAS)
        if f.endswith(".bbmodel") and os.path.isfile(os.path.join(MASCOTAS, f))
    )
    if not modelos:
        print("Sin .bbmodel en mascotas/: no se genera nada.")
        return
    destino = os.path.join(PACKS, "mascotas")
    print(f"Generando {len(modelos)} mascota(s) en packs/mascotas ...")
    subprocess.run([sys.executable, "-I", GENERADOR, destino, *modelos], check=True)


def ref_a_archivo(pack, ref, carpeta, extension):
    """'bettermodel:c/fp_x' -> packs/<pack>/assets/bettermodel/<carpeta>/c/fp_x<extension>"""
    if ":" in ref:
        ns, ruta = ref.split(":", 1)
    else:
        ns, ruta = "minecraft", ref
    return ns, os.path.join(pack, "assets", ns, carpeta, ruta + extension)


def buscar_modelos(nodo, salida):
    if isinstance(nodo, dict):
        if nodo.get("type") in ("model", "minecraft:model") and isinstance(nodo.get("model"), str):
            salida.append(nodo["model"])
        for v in nodo.values():
            buscar_modelos(v, salida)
    elif isinstance(nodo, list):
        for v in nodo:
            buscar_modelos(v, salida)


def revisar(pack):
    """Devuelve la lista de errores del pack (vacía = bien)."""
    errores = []
    nombre = os.path.basename(pack)
    espacios = set(os.listdir(os.path.join(pack, "assets")))
    for raiz, _, archivos in os.walk(pack):
        for f in archivos:
            if not (f.endswith(".json") or f.endswith(".mcmeta")):
                continue
            ruta = os.path.join(raiz, f)
            rel = os.path.relpath(ruta, pack)
            try:
                with open(ruta, encoding="utf-8") as fh:
                    datos = json.load(fh)
            except Exception as ex:
                errores.append(f"{nombre}: JSON roto {rel}: {ex}")
                continue
            partes = rel.split(os.sep)
            # items/*.json -> el modelo que usan tiene que existir
            if len(partes) > 3 and partes[0] == "assets" and partes[2] == "items":
                refs = []
                buscar_modelos(datos, refs)
                for ref in refs:
                    ns, archivo = ref_a_archivo(pack, ref, "models", ".json")
                    if ns in espacios and not os.path.exists(archivo):
                        errores.append(f"{nombre}: {rel} usa el modelo {ref}, que no existe")
            # models/*.json -> las texturas que usan tienen que existir
            if len(partes) > 3 and partes[0] == "assets" and partes[2] == "models":
                for tex in (datos.get("textures") or {}).values():
                    if not isinstance(tex, str) or tex.startswith("#"):
                        continue
                    ns, archivo = ref_a_archivo(pack, tex, "textures", ".png")
                    if ns in espacios and not os.path.exists(archivo):
                        errores.append(f"{nombre}: {rel} usa la textura {tex}, que no existe")
    return errores


def comprimir(pack, destino):
    archivos = []
    for raiz, _, nombres in os.walk(pack):
        for f in nombres:
            ruta = os.path.join(raiz, f)
            archivos.append((os.path.relpath(ruta, pack).replace(os.sep, "/"), ruta))
    archivos.sort()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, ruta in archivos:
            info = zipfile.ZipInfo(rel, date_time=FECHA_FIJA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(ruta, "rb") as fh:
                z.writestr(info, fh.read(), compresslevel=9)
    return len(archivos)


def sha1(ruta):
    h = hashlib.sha1()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def main():
    generar_mascotas()

    packs = sorted(
        os.path.join(PACKS, d) for d in os.listdir(PACKS)
        if os.path.isfile(os.path.join(PACKS, d, "pack.mcmeta"))
        and os.path.isdir(os.path.join(PACKS, d, "assets"))
    )
    errores = []
    for pack in packs:
        errores += revisar(pack)
    if errores:
        print("\nERRORES (no se armó ningún zip):")
        for e in errores:
            print("  -", e)
        sys.exit(1)

    os.makedirs(SALIDA, exist_ok=True)
    lineas = []
    for pack in packs:
        nombre = "FunkyPunky-" + os.path.basename(pack).capitalize() + ".zip"
        destino = os.path.join(SALIDA, nombre)
        temporal = destino + ".tmp"
        n = comprimir(pack, temporal)
        os.replace(temporal, destino)
        tam = os.path.getsize(destino)
        if tam > LIMITE_BYTES:
            print(f"ERROR: {nombre} pesa {tam / 1e6:.1f} MB (máximo 250 MB)")
            sys.exit(1)
        hash1 = sha1(destino)
        lineas.append(f"{nombre} {hash1} {tam}")
        print(f"{nombre}: {n} archivos, {tam / 1e6:.2f} MB, SHA-1 {hash1}")
    with open(os.path.join(SALIDA, "SHA1.txt"), "w", encoding="utf-8") as fh:
        fh.write("# archivo sha1 bytes (lo genera armar_packs.py; no editar)\n")
        fh.write("\n".join(lineas) + "\n")


if __name__ == "__main__":
    main()
