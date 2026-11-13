#!/usr/bin/env python3
"""
bb2bettermodel.py - Genera las piezas del resource pack de BetterModel (Java) para un .bbmodel,
igual que lo hace BetterModel 3.7.0 (snapshot del 12-nov-2026) en ModelManagerImpl / BlueprintElement.

Por qué existe: el servidor solo manda a los clientes el nombre del ítem de cada hueso
(`bettermodel:c/<modelo>_<hueso>`). Lo de adentro (modelos y texturas) es del pack, así que
se puede generar fuera del servidor con nombres propios (prefijo `fp_`) sin chocar con los que
BetterModel ofusca (a, b, 6e...).

Uso:
    python3 -I bb2bettermodel.py <salida> <modelo1.bbmodel> [<modelo2.bbmodel> ...]
El nombre del archivo (sin .bbmodel) es el id del modelo (igual que en plugins/BetterModel/models).
Escribe en <salida>/assets/bettermodel/{items/c,models/c,textures/item}/.

Verificado contra el pack generado por el servidor (slime_bunny, blue_wizard, demon_knight).
"""
import base64
import json
import math
import os
import re
import sys

import numpy as np

f32 = np.float32
NAMESPACE = "bettermodel"
MODEL_NS = "c"          # zipper.assets().obfuscate("model") en el servidor
PREFIJO = "fp_"         # nombres propios de modelos y texturas internos
VALID_DEG = {f32(0), f32(22.5), f32(45), f32(-22.5), f32(-45)}


# ---------- utilidades con float32 (como Java) ----------
def F(v):
    return f32(v)


def v3(a):
    return [F(a[0]), F(a[1]), F(a[2])] if a is not None else [F(0), F(0), F(0)]


def sub(a, b):
    return [F(a[i] - b[i]) for i in range(3)]


def add(a, b):
    return [F(a[i] + b[i]) for i in range(3)]


def div(a, s):
    return [F(a[i] / s) for i in range(3)]


def jfloat(x):
    """Float.toString de Java (como lo escribe Gson)."""
    x = F(x)
    if x == 0:
        return "-0.0" if math.copysign(1, float(x)) < 0 else "0.0"
    ax = abs(float(x))
    if 1e-3 <= ax < 1e7:
        s = np.format_float_positional(x, unique=True, trim="0")
        if "." not in s:
            s += ".0"
        if s.endswith("."):
            s += "0"
        return s
    s = np.format_float_scientific(x, unique=True, trim="0", exp_digits=1)
    m, e = s.split("e")
    if "." not in m or m.endswith("."):
        m = m.rstrip(".") + ".0"
    return m + "E" + str(int(e))


class JF:
    def __init__(self, v):
        self.v = v


def dumps(o):
    if isinstance(o, JF):
        return jfloat(o.v)
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(k) + ":" + dumps(v) for k, v in o.items()) + "}"
    if isinstance(o, list):
        return "[" + ",".join(dumps(v) for v in o) + "]"
    if isinstance(o, bool):
        return "true" if o else "false"
    if isinstance(o, (int, np.integer)):
        return str(int(o))
    if isinstance(o, (float, np.floating)):
        return jfloat(o)
    return json.dumps(o, ensure_ascii=False)


def jarr(a):
    return [JF(x) for x in a]


def to_pack_name(raw):
    # PackUtil.toPackName: minúsculas; lo que no sea [a-z0-9_.] -> hashCode(String) en hexadecimal
    def rep(m):
        h = 0
        for ch in m.group(0):
            h = (31 * h + ord(ch)) & 0xFFFFFFFF
        if h >= 2**31:
            h -= 2**32
        return format(h, "x") if h >= 0 else "-" + format(-h, "x")
    return re.sub(r"[^a-z0-9_.]", rep, raw.lower())


# ---------- cuaterniones (JOML) ----------
def rotate_zyx(az, ay, ax):
    sx, cx = math.sin(ax * 0.5), math.cos(ax * 0.5)
    sy, cy = math.sin(ay * 0.5), math.cos(ay * 0.5)
    sz, cz = math.sin(az * 0.5), math.cos(az * 0.5)
    cycz, sysz, sycz, cysz = cy * cz, sy * sz, sy * cz, cy * sz
    w = cx * cycz + sx * sysz
    x = sx * cycz - cx * sysz
    y = cx * sycz + sx * cysz
    z = cx * cysz - sx * sycz
    return (x, y, z, w)


def q_zyx_deg(r):
    d = math.pi / 180
    return rotate_zyx(float(r[2]) * d, float(r[1]) * d, float(r[0]) * d)


def q_invert(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    return (-x / n, -y / n, -z / n, w / n)


def q_rot(q, v):
    x, y, z, w = q
    vx, vy, vz = (float(c) for c in v)
    # v' = q v q*
    xx, yy, zz = x * x, y * y, z * z
    ww = w * w
    xy, xz, yz = x * y, x * z, y * z
    xw, zw, yw = x * w, z * w, y * w
    k = 1 / (xx + yy + zz + ww)
    rx = ((ww + xx - zz - yy) * vx + (-zw + xy - zw + xy) * vy + (yw + xz + xz + yw) * vz) * k
    ry = ((xy + zw + zw + xy) * vx + (yy - zz + ww - xx) * vy + (yz + yz - xw - xw) * vz) * k
    rz = ((xz - yw + xz - yw) * vx + (yz + yz + xw + xw) * vy + (zz - yy - xx + ww) * vz) * k
    return [F(rx), F(ry), F(rz)]


def to_mc_degree(r):
    qx, qy, qz, qw = (F(c) for c in q_zyx_deg(r))
    sy = F(2.0) * (qx * qz + qw * qy)
    m00 = F(1.0) - F(2.0) * (qy * qy + qz * qz)
    m10 = F(2.0) * (qx * qy - qw * qz)
    y = F(math.atan2(sy, math.hypot(m00, m10)))
    if abs(sy) < F(0.99999):
        x = F(math.atan2(F(2.0) * (qw * qx - qy * qz), F(1.0) - F(2.0) * (qx * qx + qy * qy)))
        z = F(math.atan2(-m10, m00))
    else:
        x = F(math.atan2(F(2.0) * (qy * qz + qw * qx), F(1.0) - F(2.0) * (qx * qx + qz * qz)))
        z = F(0)
    k = F(180 / math.pi)
    return [F(x * k), F(y * k), F(z * k)]


def identifier(rot):
    n = sum(1 for c in rot if c != 0)
    if n < 2 and all(c in VALID_DEG for c in rot):
        return [F(0)] * 3
    return rot


# ---------- generación ----------
def build_model(path, out):
    name = os.path.splitext(os.path.basename(path))[0]
    d = json.load(open(path, encoding="utf-8"))
    res = d.get("resolution", {"width": 16, "height": 16})
    elements = {e["uuid"]: e for e in d["elements"]}
    groups = {g["uuid"]: g for g in d.get("groups", [])}

    # Texturas
    texs = []
    for i, t in enumerate(d["textures"]):
        tname = os.path.splitext(t["name"])[0]
        packname = PREFIJO + to_pack_name(tname if tname.startswith("global_") else name + "_" + tname)
        uvw, uvh = t.get("uv_width", 0), t.get("uv_height", 0)
        w, h = t.get("width", 0), t.get("height", 0)
        if uvw > 0 and uvh > 0 and not (res["width"] == w and res["height"] == h):
            r = (uvw, uvh)
        else:
            r = (res["width"], res["height"])
        texs.append({"pack": packname, "res": r, "src": t["source"], "w": w, "h": h, "uvw": uvw, "uvh": uvh,
                     "render": not tname.startswith("-"), "glow": tname.endswith("_e") or t.get("render-mode") in ("emissive", "additive"),
                     "ft": t.get("frame_time", 0), "fi": t.get("frame_interpolate", False)})
    used_tex = set()
    items = {}
    models = {}

    def face_json(uv, ti):
        r = texs[ti]["res"]
        wd, hd = F(r[0]) / F(16), F(r[1]) / F(16)
        u = [F(uv[0]) / wd, F(uv[1]) / hd, F(uv[2]) / wd, F(uv[3]) / hd]
        if not all(F(0) <= c <= F(16) for c in u):
            return None
        o = {"uv": jarr(u)}
        return o

    def cube_json(c, scale, gorigin, ident, glow_group):
        corigin = v3(c.get("origin"))
        center = div(sub(corigin, gorigin), scale)
        qi = q_invert(q_zyx_deg(ident))
        rel = add(sub(q_rot(qi, center), center), [F(8)] * 3)
        infl = F(F(c.get("inflate", 0)) / scale)
        fr = [F(x - infl) for x in add(div(sub(v3(c.get("from")), gorigin), scale), rel)]
        to = [F(x + infl) for x in add(div(sub(v3(c.get("to")), gorigin), scale), rel)]
        r = sub(v3(c.get("rotation")), ident)
        rot = None
        if any(x != 0 for x in r):
            o = add(center, rel)
            rot = {}
            if abs(r[0]) > 0:
                rot["angle"], rot["axis"] = JF(r[0]), "x"
            elif abs(r[1]) > 0:
                rot["angle"], rot["axis"] = JF(r[1]), "y"
            elif abs(r[2]) > 0:
                rot["angle"], rot["axis"] = JF(r[2]), "z"
            rot["origin"] = jarr(o)
        faces = {}
        for fid in ("north", "south", "east", "west", "up", "down"):
            f = (c.get("faces") or {}).get(fid)
            if not f or not isinstance(f.get("texture"), int):
                continue
            ti = f["texture"]
            fj = face_json(f["uv"], ti)
            if fj is None:
                continue
            if f.get("rotation", 0):
                fj["rotation"] = int(f["rotation"])
            fj["tintindex"] = 0
            fj["texture"] = "#" + str(ti)
            faces[fid] = fj
        if not faces:
            return []
        light = 15 if (glow_group or any(texs[f["texture"]]["glow"] for f in (c.get("faces") or {}).values()
                                        if isinstance(f.get("texture"), int))) else (
            15 if "glow" in c.get("name", "").lower() else (c.get("light_emission", 0) or None))
        o = {}
        if light:
            o["light_emission"] = light
        o["from"] = jarr(fr)
        o["to"] = jarr(to)
        o["faces"] = faces
        if rot is not None:
            o["rotation"] = rot
        return [o]

    def walk(node):
        if isinstance(node, str):
            return
        g = dict(groups.get(node["uuid"], {}))
        g.update({k: v for k, v in node.items() if k not in ("children", "isOpen")})
        bone = g.get("name", "bone")
        gorigin = v3(g.get("origin"))
        cubes = [elements[c] for c in node.get("children", []) if isinstance(c, str)
                 and c in elements and elements[c].get("type", "cube") == "cube"]
        if cubes:
            scale = F(1)
            mx = F(1)
            for c in cubes:
                fr, to = sub(v3(c.get("from")), gorigin), sub(v3(c.get("to")), gorigin)
                m = max([F(0)] + [abs(x) for x in fr + to])
                mx = max(mx, F(m / F(16)))
            scale = mx
            glow_group = "glow" in bone.lower()
            buckets = {}
            for c in cubes:
                ident = identifier(v3(c.get("rotation")))
                buckets.setdefault(tuple(float(x) for x in ident), (ident, []))[1].append(c)
            jsonname = to_pack_name(name + "_" + bone)
            parts = []
            for n, (ident, cs) in enumerate(buckets.values(), 1):
                tex_ids = sorted({f["texture"] for c in cs for f in (c.get("faces") or {}).values()
                                  if isinstance(f.get("texture"), int)})
                if not tex_ids:
                    continue
                els = [e for c in cs for e in cube_json(c, scale, gorigin, ident, glow_group)]
                textures = {str(i): f"{NAMESPACE}:item/{texs[i]['pack']}" for i in tex_ids}
                textures["particle"] = textures[str(tex_ids[0])]
                used_tex.update(tex_ids)
                m = {"textures": textures, "elements": els}
                if any(x != 0 for x in ident):
                    m["display"] = {"fixed": {"rotation": jarr(to_mc_degree(ident))}}
                mname = PREFIJO + jsonname + "_" + str(n)
                models[mname] = m
                parts.append(mname)
            if parts:
                def ref(p):
                    return {"type": "model", "model": f"{NAMESPACE}:{MODEL_NS}/{p}",
                            "tints": [{"type": "custom_model_data", "default": 16777215}]}
                body = ref(parts[0]) if len(parts) == 1 else {"type": "composite", "models": [ref(p) for p in parts]}
                items[jsonname] = {"model": body}
        for ch in node.get("children", []):
            walk(ch)

    for root in d["outliner"]:
        walk(root)

    base = os.path.join(out, "assets", NAMESPACE)
    for sub_ in ("items/" + MODEL_NS, "models/" + MODEL_NS, "textures/item"):
        os.makedirs(os.path.join(base, sub_), exist_ok=True)
    for k, v in items.items():
        open(os.path.join(base, "items", MODEL_NS, k + ".json"), "w").write(dumps(v))
    for k, v in models.items():
        open(os.path.join(base, "models", MODEL_NS, k + ".json"), "w").write(dumps(v))
    for i in sorted(used_tex):
        t = texs[i]
        if not t["render"]:
            continue
        data = base64.b64decode(t["src"].split(",", 1)[1])
        open(os.path.join(base, "textures", "item", t["pack"] + ".png"), "wb").write(data)
        anim = (t["h"] / t["uvh"] > t["w"] / t["uvw"]) if (t["uvw"] > 0 and t["uvh"] > 0) else (t["w"] > 0 and t["h"] // max(t["w"], 1) > 1)
        if anim:
            open(os.path.join(base, "textures", "item", t["pack"] + ".png.mcmeta"), "w").write(
                dumps({"animation": {"interpolate": bool(t["fi"]), "frametime": int(t["ft"])}}))
    return name, sorted(items)


if __name__ == "__main__":
    out = sys.argv[1]
    for p in sys.argv[2:]:
        n, its = build_model(p, out)
        print(n, len(its), "huesos:", ", ".join(i[len(n) + 1:] for i in its))
