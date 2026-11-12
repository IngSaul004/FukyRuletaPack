"""Convierte un .bbmodel (Blockbench 4/5) a la carpeta que espera GeyserModelEngineExtension.

Replica el complemento oficial GeyserModelEngineBlockbenchPacker:
  <modelo>/<modelo>.geo.json, <modelo>.animation.json, <textura>.png, config.json
Uso: python3 -I bb2gme.py modelo.bbmodel carpeta_salida
"""
import base64, json, math, os, re, sys

src, out_root = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf-8"))
name = d.get("name") or os.path.splitext(os.path.basename(src))[0]
tex_w = d.get("resolution", {}).get("width", 16)
tex_h = d.get("resolution", {}).get("height", 16)

elements = {e["uuid"]: e for e in d.get("elements", [])}
groups = {g["uuid"]: g for g in d.get("groups", [])}   # formato 5.0
textures = d.get("textures", [])

def tex_key(n):
    return re.sub(r"(\.(png|jpe?g|webp|tga))+$", "", n, flags=re.I)

def num(v):
    if isinstance(v, (int, float)): return v
    try: return float(v)
    except Exception: return v          # molang: se deja como texto

def clean(v):
    return int(v) if isinstance(v, float) and v.is_integer() else round(v, 4) if isinstance(v, float) else v

# ---------- recorrer el outliner (orden = getAllGroups de Blockbench) ----------
ordered = []   # (grupo, padre, [elementos])
def group_of(node):
    if isinstance(node, dict):
        g = dict(groups.get(node["uuid"], {}))
        g.update({k: v for k, v in node.items() if k != "children"})
        return g, node.get("children", [])
    return None, None

def walk(nodes, parent):
    for n in nodes:
        if isinstance(n, dict):
            g, ch = group_of(n)
            cubes = [elements[c] for c in ch if isinstance(c, str) and c in elements]
            ordered.append((g, parent, cubes))
            walk([c for c in ch if isinstance(c, dict)], g)

loose = [elements[c] for c in d.get("outliner", []) if isinstance(c, str) and c in elements]
if loose:
    ordered.append(({"name": "bb_main", "origin": [0, 0, 0], "rotation": [0, 0, 0]}, None, loose))
walk(d.get("outliner", []), None)

# ---------- geometría ----------
config = {"head_rotation": True, "material": "entity_alphatest_change_color_one_sided",
          "blend_transition": True, "per_texture_uv_size": {}, "binding_bones": {}, "anim_textures": {}}
face_rotation = False

def compile_cube(c):
    fr, to = c["from"], c["to"]
    size = [to[i] - fr[i] for i in range(3)]
    t = {"origin": [-(fr[0] + size[0]), fr[1], fr[2]], "size": size}
    if c.get("inflate"): t["inflate"] = c["inflate"]
    rot = c.get("rotation", [0, 0, 0])
    if any(rot):
        piv = list(c.get("origin", [0, 0, 0])); piv[0] *= -1
        t["pivot"] = piv
        t["rotation"] = [-rot[0], -rot[1], rot[2]]
    if c.get("box_uv"):
        t["uv"] = c.get("uv_offset", [0, 0])
        return t, {None: list(c.get("faces", {}).keys())}
    uv = {}
    by_tex = {}
    global face_rotation
    for k, f in c.get("faces", {}).items():
        if f.get("texture") is None: continue
        u = f["uv"]
        e = {"uv": [u[0], u[1]], "uv_size": [u[2] - u[0], u[3] - u[1]]}
        if f.get("rotation"): e["uv_rotation"] = f["rotation"]; face_rotation = True
        if k in ("up", "down"):
            e["uv"] = [e["uv"][0] + e["uv_size"][0], e["uv"][1] + e["uv_size"][1]]
            e["uv_size"] = [-e["uv_size"][0], -e["uv_size"][1]]
        uv[k] = {kk: [clean(x) for x in vv] if isinstance(vv, list) else vv for kk, vv in e.items()}
        by_tex.setdefault(f["texture"], []).append(k)
    t["uv"] = uv
    return t, by_tex

def texture_name(idx):
    if idx is None or not isinstance(idx, int) or idx >= len(textures): return None
    return textures[idx]["name"]

bones, all_min, all_max = [], [math.inf] * 3, [-math.inf] * 3
for g, parent, cubes in ordered:
    if g.get("export") is False or not g.get("name") or g["name"].startswith("b_"): continue
    bone = {"name": g["name"]}
    if parent is not None: bone["parent"] = parent["name"]
    piv = list(g.get("origin", [0, 0, 0])); piv[0] *= -1
    bone["pivot"] = piv
    rot = g.get("rotation", [0, 0, 0])
    if any(rot): bone["rotation"] = [-rot[0], -rot[1], rot[2]]
    per_tex = {}
    for c in cubes:
        if c.get("export") is False or c.get("type", "cube") != "cube": continue
        tmpl, by_tex = compile_cube(c)
        for i in range(3):
            all_min[i] = min(all_min[i], c["from"][i]); all_max[i] = max(all_max[i], c["to"][i])
        keys = list(by_tex.keys())
        split = len(keys) > 1 and not c.get("box_uv")
        for tidx in keys:
            tn = texture_name(tidx) if tidx is not None else (textures[0]["name"] if textures else None)
            if tn is None: continue
            t2 = json.loads(json.dumps(tmpl))
            if split: t2["uv"] = {k: v for k, v in t2["uv"].items() if k in by_tex[tidx]}
            per_tex.setdefault(tn, []).append(t2)
            if not split: break
    multi = len(per_tex) > 1
    extra = []
    for i, (tn, cl) in enumerate(per_tex.items()):
        key = tex_key(tn)
        if multi:
            nb = {"name": f"uv_{bone['name']}{i}", "pivot": [0, 0, 0], "parent": bone["name"], "cubes": cl}
            extra.append(nb); config["binding_bones"].setdefault(key, []).append(nb["name"])
        else:
            bone["cubes"] = cl; config["binding_bones"].setdefault(key, []).append(bone["name"])
    bones.append(bone); bones.extend(extra)

if all_min[0] == math.inf: all_min, all_max = [0, 0, 0], [0, 0, 0]
radius = max(abs(all_min[0]), abs(all_max[0]), abs(all_min[2]), abs(all_max[2]))
vb_w = max(1, math.ceil(radius * 2 / 16) + 1)
y0, y1 = math.floor(all_min[1] / 16), math.ceil(all_max[1] / 16)
vb_h = max(1, y1 - y0 + 1)

geo = {"format_version": "1.21.0" if face_rotation else "1.12.0",
       "minecraft:geometry": [{"description": {
           "identifier": "geometry." + (d.get("model_identifier") or name),
           "texture_width": tex_w, "texture_height": tex_h,
           "visible_bounds_width": vb_w, "visible_bounds_height": vb_h,
           "visible_bounds_offset": [0, (y0 + y1) / 2, 0]},
           "bones": bones}]}

# ---------- animaciones (formato Bedrock 1.8.0) ----------
def tcode(t):
    t = round(float(t), 4)
    s = ("%.4f" % t).rstrip("0").rstrip(".")
    return s + ".0" if "." not in s else s

anims = {}
for a in d.get("animations", []):
    out = {}
    loop = a.get("loop", "once")
    if loop == "loop": out["loop"] = True
    elif loop == "hold": out["loop"] = "hold_on_last_frame"
    if a.get("override"): out["override_previous_animation"] = True
    if a.get("length"): out["animation_length"] = a["length"]
    bones_out = {}
    for an in a.get("animators", {}).values():
        if an.get("type", "bone") != "bone": continue
        chans = {}
        for kf in an.get("keyframes", []):
            ch = kf["channel"]
            if ch not in ("rotation", "position", "scale"): continue
            dp = kf["data_points"]
            vec = lambda p: [clean(num(p.get(ax, 0))) for ax in "xyz"]
            interp = kf.get("interpolation", "linear")
            if len(dp) > 1:
                val = {"pre": vec(dp[0]), "post": vec(dp[1])}
            elif interp == "catmullrom":
                val = {"post": vec(dp[0]), "lerp_mode": "catmullrom"}
            else:
                val = vec(dp[0])
            chans.setdefault(ch, {})[tcode(kf["time"])] = val
        for ch, frames in chans.items():
            frames = dict(sorted(frames.items(), key=lambda kv: float(kv[0])))
            bones_out.setdefault(an["name"], {})[ch] = frames
    if bones_out: out["bones"] = bones_out
    anims[a["name"]] = out

# ---------- escribir ----------
folder = os.path.join(out_root, name)
os.makedirs(folder, exist_ok=True)
for t in textures:
    key = tex_key(t["name"])
    src_b64 = t.get("source", "")
    if src_b64.startswith("data:"):
        open(os.path.join(folder, key + ".png"), "wb").write(base64.b64decode(src_b64.split(",", 1)[1]))
    config["per_texture_uv_size"][key] = [t.get("uv_width", tex_w), t.get("uv_height", tex_h)]
    fr = t.get("frame_time")
    if t.get("height") and t.get("width") and t["height"] > t["width"] and t["height"] % t["width"] == 0 and t.get("frame_order_type"):
        frames = t["height"] // t["width"]
        if frames > 1:
            config["anim_textures"][key] = {"frames": frames, "fps": (20 / fr) if fr else 7}
json.dump(geo, open(os.path.join(folder, name + ".geo.json"), "w"), separators=(",", ":"))
if anims:
    json.dump({"format_version": "1.8.0", "animations": anims},
              open(os.path.join(folder, name + ".animation.json"), "w"), separators=(",", ":"))
json.dump(config, open(os.path.join(folder, "config.json"), "w"), separators=(",", ":"))
print("OK", folder, "| huesos:", [b["name"] for b in bones], "| animaciones:", list(anims), "| texturas:", list(config["per_texture_uv_size"]))
