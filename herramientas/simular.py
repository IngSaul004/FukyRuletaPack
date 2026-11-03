# Simula como Minecraft Java arma los textos de la fuente funkypunky:ruleta (avance, ascent,
# espacios, tinte por color) y como Bedrock muestra su glifo. Sirve para revisar uniones y
# hacer la vista previa animada.  Uso: python3 -I simular.py <out> <px_por_unidad> <salida>
import json, math, os, re, sys
from PIL import Image

OUT, PPU, DEST = sys.argv[1], float(sys.argv[2]), sys.argv[3]
fuente = json.load(open(os.path.join(OUT, 'java/assets/funkypunky/font/ruleta.json')))
glifos, espacios = {}, {}
for p in fuente['providers']:
    if p['type'] == 'space':
        for c, a in p['advances'].items():
            espacios[c] = a
    else:
        ruta = os.path.join(OUT, 'java/assets/funkypunky/textures', p['file'].split(':')[1])
        im = Image.open(ruta).convert('RGBA')
        f = p['height'] / im.height
        # ancho real: ultima columna con alfa (como Minecraft)
        a = im.getchannel('A')
        ancho = max(x + 1 for x in range(im.width) if a.crop((x, 0, x + 1, im.height)).getextrema()[1] > 0)
        avance = int(0.5 + ancho * f) + 1
        w = max(1, round(im.width * f * PPU)); h = round(p['height'] * PPU)
        glifos[p['chars'][0]] = (im.resize((w, h), Image.NEAREST), p['ascent'], avance)

src = open(os.path.join(OUT, 'Sprites.java'), encoding='utf-8').read()
def arr(nombre):
    m = re.search(r'static final String\[\] ' + nombre + r' = \{(.*?)\};', src, re.S)
    return [bytes(s, 'ascii').decode('unicode_escape') for s in re.findall(r'"((?:\\u[0-9A-F]{4})*)"', m.group(1))]
def arr2(nombre):
    m = re.search(r'static final String\[\]\[\] ' + nombre + r' = \{(.*?)\n    \};', src, re.S)
    return [[bytes(s, 'ascii').decode('unicode_escape') for s in re.findall(r'"((?:\\u[0-9A-F]{4})*)"', fila)]
            for fila in re.findall(r'\{([^{}]*)\}', m.group(1))]
SP = {k: arr(k) for k in ['GAJO', 'MARCA', 'ARO', 'FLECHA', 'LOGO', 'LOGO_POP', 'RELLENO', 'BRILLO', 'ENTRADA', 'BE_GIRO', 'BE_ENTRADA']}
SP['BE_RELLENO'] = arr2('BE_RELLENO'); SP['BE_FINAL'] = arr2('BE_FINAL')
COLORES = [int(x, 16) for x in re.findall(r'0x([0-9A-F]{6})', re.search(r'COLORES = \{(.*?)\}', src).group(1))]

W = H = int(64 * PPU)
def componer(capas, fondo=(58, 92, 64, 255)):
    """capas: lista de (texto, rgb). Linea base en el centro vertical; x=0 en el centro (ancho total 0)."""
    lienzo = Image.new('RGBA', (W, H), fondo)
    ox, base = W / 2, H / 2 - 5 * PPU
    x = 0
    for texto, rgb in capas:
        for c in texto:
            if c in espacios:
                x += espacios[c]; continue
            im, asc, av = glifos[c]
            if rgb != 0xFFFFFF:
                r, g, b = rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255
                ch = im.split()
                im = Image.merge('RGBA', (ch[0].point(lambda v: v * r // 255), ch[1].point(lambda v: v * g // 255),
                                          ch[2].point(lambda v: v * b // 255), ch[3]))
            lienzo.alpha_composite(im, (round(ox + x * PPU), round(base - asc * PPU)))
            x += av
    assert x == 0, x
    return lienzo

# ---------------- secuencia (misma logica que Giro.java, valores por defecto del config)
def secuencia(seg=1, vueltas=2, duracion=180, pausa_inicio=12, latidos=3, pausa_final=30):
    pasos = []
    logo = lambda: SP['LOGO'][len(pasos) % len(SP['LOGO'])]
    aro_lento = lambda: (len(pasos) // 4) % 2
    def gajos(c, f):
        for s in range(8): c.append((SP['GAJO'][(12 * s + f) % 96], COLORES[s]))
        for s in range(8): c.append((SP['MARCA'][(12 * s + f) % 96], 0xFFFFFF))
    def ruleta(f, aro, golpe):
        c = []; gajos(c, f)
        return c + [(SP['ARO'][aro], 0xFFFFFF), (logo(), 0xFFFFFF), (SP['FLECHA'][golpe], 0xFFFFFF)]
    for p in range(len(SP['ENTRADA'])): pasos.append([(SP['ENTRADA'][p], 0xFFFFFF)])
    for i in range(pausa_inicio): pasos.append(ruleta(0, aro_lento(), 0))
    fin = (96 - 12 * seg - 6) % 96
    obj = vueltas * 96 + fin; ant = 0
    for t in range(1, duracion + 1):
        x = t / duracion; cuadro = round(obj * (1 - (1 - x) ** 3))
        cruzo = cuadro // 12 != ant // 12
        aro = (len(pasos) // 2) % 2 if x < 0.75 else aro_lento()
        pasos.append(ruleta(cuadro % 96, aro, 1 if cruzo else 0)); ant = cuadro
    for i in range(6): pasos.append(ruleta(fin, 2 if (i // 2) % 2 == 0 else 0, 0))
    col = COLORES[seg]
    for k, dur in enumerate([1, 1, 1, 1, 1, 2, 2, 2, 2, 2]):
        for r in range(dur):
            c = []
            if k < 9: gajos(c, fin)
            c += [(SP['RELLENO'][k], col), (SP['ARO'][2], 0xFFFFFF), (logo(), 0xFFFFFF), (SP['FLECHA'][0], 0xFFFFFF)]
            pasos.append(c)
    for l in range(latidos):
        for k in range(8):
            c = [(SP['RELLENO'][9], col)]
            if l == 0 and k < 6: c.append((SP['BRILLO'][k], 0xFFFFFF))
            c += [(SP['ARO'][2 if k % 4 < 2 else l % 2], 0xFFFFFF), (SP['LOGO_POP'][k], 0xFFFFFF), (SP['FLECHA'][0], 0xFFFFFF)]
            pasos.append(c)
    lleno = lambda: [(SP['RELLENO'][9], col), (SP['ARO'][aro_lento()], 0xFFFFFF), (logo(), 0xFFFFFF), (SP['FLECHA'][0], 0xFFFFFF)]
    for i in range(pausa_final): pasos.append(lleno())
    pasos.append(lleno())
    return pasos

if __name__ == '__main__':
    os.makedirs(DEST, exist_ok=True)
    pasos = secuencia()
    print('ticks', len(pasos), '=', len(pasos) / 20, 's (+0.9 s de desvanecido)')
    for n, i in enumerate(range(len(pasos))):
        componer(pasos[i]).convert('RGB').save(os.path.join(DEST, f'f{n:04d}.png'))
    # desvanecido (lo hace el juego): 18 cuadros
    ult = componer(pasos[-1], fondo=(0, 0, 0, 0))
    for k in range(18):
        a = 1 - (k + 1) / 18
        bg = Image.new('RGBA', ult.size, (58, 92, 64, 255))
        u = ult.copy(); u.putalpha(u.getchannel('A').point(lambda v: int(v * a)))
        bg.alpha_composite(u); bg.convert('RGB').save(os.path.join(DEST, f'f{len(pasos) + k:04d}.png'))
