# -*- coding: utf-8 -*-
"""
FUNKY PUNKY MC - Generador de la ruleta HD (pack 4 / FunkyRuleta 1.3.0)

Por que "por piezas":
  Minecraft Java no carga una letra de fuente de mas de 256x256 px. Una ruleta entera en 256 px
  se estira ~3.5 veces en pantalla y se ve pixeleada. Aqui la ruleta se dibuja a ~683 px y se
  corta en piezas de hasta 256 px; el plugin las vuelve a juntar con "espacios negativos".

Por que "en blanco":
  Los gajos y el relleno se dibujan en escala de grises. Minecraft multiplica cada letra por el
  color del texto, asi que el plugin los pinta del color de cada categoria. Una sola imagen sirve
  para los 8 colores (y el relleno del ganador no necesita 8 juegos de imagenes).

Uso:  python3 -I generar_ruleta_hd.py <logo.png> <carpeta_salida>
Salida: pack de Java (fuente funkypunky:ruleta), pagina glyph_E2.png de Bedrock,
        Sprites.java para el plugin y vistas previas.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import map_coordinates

# ------------------------------------------------------------------ medidas
TILE = 256                 # px maximos por letra (limite de Minecraft Java)
ALTO_U = 21                # alto de cada pieza en "unidades" de fuente
S = TILE / ALTO_U          # px por unidad (12.19)
SS = 3                     # supermuestreo (bordes suaves)
CY = -7                    # centro de la ruleta respecto a la linea base (unidades, + = arriba)

R_DISCO = 18.5             # radio de los gajos
R_ARO_IN = 18.2
R_ARO_OUT = 22.4
R_FOCOS = 20.3
N_FOCOS = 24
R_CENTRO = 6.9             # placa del logo
CUADROS = 96               # posiciones de giro (3.75 grados)
N_LOGO = 24                # cuadros del logo en bucle (1.2 s)
N_POP = 8                  # cuadros del "salto" del logo al ganar
N_RELLENO = 10             # cuadros del relleno de color
N_BRILLO = 6               # cuadros del brillo sobre el color
ESCALAS_ENTRADA = [0.18, 0.42, 0.68, 0.9, 1.04, 1.05, 1.01]

# Color de cada segmento (0 = arriba a la derecha y sigue en el sentido del reloj).
# Mismo orden que config.yml: naranja, rosa, cian, rojo, morado, amarillo, azul, verde.
COLORES = [0xFFA522, 0xFF55FF, 0x4FF0FF, 0xFF4F5E, 0xB52BD8, 0xFFE45C, 0x5F6BFF, 0x5CF06A]

# Paleta FUNKY PUNKY
MAGENTA = (1.0, 0.25, 1.0)
MORADO_OSC = (0.17, 0.0, 0.26)
CONTORNO = (0.13, 0.0, 0.2)


def hexf(c):
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)


# ------------------------------------------------------------------ utilidades de dibujo
def capa(shape):
    return np.zeros(shape + (4,), np.float32)


def suave(d, ancho):
    """0 -> 1 en una franja de 'ancho' alrededor de d = 0 (borde antialias analitico)."""
    return np.clip(0.5 + d / ancho, 0.0, 1.0)


def pintar(dst, mask, color, alpha=1.0):
    """Pone un color (premultiplicado) encima de dst con la mascara dada."""
    a = (mask * alpha)[..., None]
    col = np.empty(mask.shape + (4,), np.float32)
    if isinstance(color, np.ndarray) and color.ndim == 3:
        col[..., :3] = color
    else:
        col[..., :3] = np.asarray(color, np.float32)
    col[..., 3] = 1.0
    src = col * a
    dst[:] = src + dst * (1 - src[..., 3:4])


def encima(abajo, arriba):
    return arriba + abajo * (1 - arriba[..., 3:4])


def polar(U, V):
    r = np.hypot(U, V)
    th = np.degrees(np.arctan2(U, V)) % 360.0   # 0 = arriba, sentido del reloj
    return r, th


def dang(a, b):
    """Diferencia angular con signo a-b en (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def muestrear(img, X, Y):
    """img: arreglo HxWx4 premultiplicado; X,Y en px de la imagen (float)."""
    out = np.empty(X.shape + (4,), np.float32)
    for c in range(4):
        out[..., c] = map_coordinates(img[..., c], [Y, X], order=1, mode='constant', cval=0.0)
    return out


def imagen_premult(im):
    a = np.asarray(im.convert('RGBA'), np.float32) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a


# ------------------------------------------------------------------ recursos (logo y "?")
def preparar_logo(ruta):
    im = Image.open(ruta).convert('RGBA')
    im = im.crop(im.getbbox())
    ancho = 640
    im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
    return imagen_premult(im)


def preparar_interrogacion():
    fuente = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 300)
    im = Image.new('RGBA', (360, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((180, 215), '?', font=fuente, anchor='mm', fill=(255, 255, 255, 255),
           stroke_width=26, stroke_fill=(40, 6, 58, 255))
    im = im.crop(im.getbbox())
    return imagen_premult(im)


# ------------------------------------------------------------------ capas (funciones de U,V)
def gajo(U, V, i):
    """Gajo i: de 3.75*i a 3.75*i+45 grados (blanco/gris, se tine con el color del texto)."""
    r, th = polar(U, V)
    a0 = 3.75 * i
    d0 = dang(th, a0)                      # dentro si 0 <= d0 <= 45
    dentro_ang = np.minimum(d0, 45.0 - d0)  # grados hasta la orilla mas cercana
    dist_lado = np.where(dentro_ang > 0, r * np.sin(np.radians(np.clip(dentro_ang, 0, 90))), -1)
    px = 1.0 / S
    a = suave(R_DISCO - r, px) * suave(dist_lado, px)
    a *= (d0 > -10) & (d0 < 55)
    t = np.clip(r / R_DISCO, 0, 1)
    v = 0.74 + 0.26 * t ** 1.4                        # mas claro hacia afuera
    v = v * (1 - 0.18 * suave(r - (R_DISCO - 1.2), 1.6))  # sombra interior junto al aro
    brillo = np.exp(-((dentro_ang - 9) / 7.0) ** 2) * 0.08 * t
    v = np.clip(v + brillo, 0, 1)
    linea = suave(0.16 - dist_lado, px)               # separador oscuro
    v = v * (1 - linea) + 0.18 * linea
    out = capa(U.shape)
    out[..., :3] = (v * a)[..., None]
    out[..., 3] = a
    return out


def marca(U, V, i, INT):
    """'?' blanco del gajo i, girado con la ruleta (no se tine)."""
    thc = math.radians(3.75 * i + 22.5)
    rc = 12.9
    cu, cv = rc * math.sin(thc), rc * math.cos(thc)
    du, dv = U - cu, V - cv
    arriba = (math.sin(thc), math.cos(thc))
    der = (math.cos(thc), -math.sin(thc))
    ly = du * arriba[0] + dv * arriba[1]
    lx = du * der[0] + dv * der[1]
    alto = 5.2
    esc = INT.shape[0] / alto
    X = INT.shape[1] / 2 + lx * esc
    Y = INT.shape[0] / 2 - ly * esc
    return muestrear(INT, X, Y)


def aro(U, V, modo):
    """Aro morado con focos. modo 0/1 = focos alternados, 2 = todos encendidos (ganador)."""
    r, th = polar(U, V)
    px = 1.0 / S
    out = capa(U.shape)
    # sombra suave por fuera
    sombra = np.clip(1 - (r - R_ARO_OUT) / 0.9, 0, 1) * (r > R_ARO_OUT - 0.3) * 0.45
    pintar(out, sombra, (0.05, 0.0, 0.08))
    m = suave(r - R_ARO_IN, px) * suave(R_ARO_OUT - r, px)
    t = np.clip((r - R_ARO_IN) / (R_ARO_OUT - R_ARO_IN), 0, 1)
    # perfil: orilla oscura, bisel claro, cuerpo magenta, bisel, orilla oscura
    paradas = [(0.0, (0.16, 0.0, 0.24)), (0.1, (0.55, 0.05, 0.62)), (0.22, (1.0, 0.45, 1.0)),
               (0.5, (0.86, 0.12, 0.9)), (0.8, (0.6, 0.04, 0.68)), (0.9, (0.95, 0.4, 0.98)),
               (1.0, (0.16, 0.0, 0.24))]
    col = np.zeros(U.shape + (3,), np.float32)
    for k in range(len(paradas) - 1):
        t0, c0 = paradas[k]
        t1, c1 = paradas[k + 1]
        w = np.clip((t - t0) / (t1 - t0), 0, 1)[..., None]
        sel = ((t >= t0) & (t <= t1))[..., None]
        col = np.where(sel, np.asarray(c0) * (1 - w) + np.asarray(c1) * w, col)
    luz = 1 + 0.14 * np.cos(np.radians(th - 315))  # luz desde arriba a la izquierda
    col = np.clip(col * luz[..., None], 0, 1)
    pintar(out, m, col)
    # focos
    for k in range(N_FOCOS):
        ang = math.radians(k * 360 / N_FOCOS + 7.5)
        fu, fv = R_FOCOS * math.sin(ang), R_FOCOS * math.cos(ang)
        d = np.hypot(U - fu, V - fv)
        encendido = modo == 2 or (k % 2 == modo)
        base = suave(0.78 - d, px)
        pintar(out, suave(0.98 - d, px), (0.2, 0.0, 0.28))  # engaste
        if encendido:
            halo = np.clip(1 - d / 2.0, 0, 1) ** 2 * (0.75 if modo == 2 else 0.55)
            pintar(out, halo * (d > 0.7), (1.0, 0.92, 0.55))
            centro = np.clip(1 - d / 0.78, 0, 1)
            colf = np.stack([np.ones_like(d), 0.86 + 0.14 * centro, 0.42 + 0.58 * centro], -1)
            pintar(out, base, colf)
        else:
            pintar(out, base, (0.42, 0.12, 0.45))
            pintar(out, suave(0.3 - np.hypot(U - fu + 0.22, V - fv - 0.22), px), (0.62, 0.3, 0.66), 0.8)
    return out


def flecha(U, V, golpe):
    """Flecha arriba, apuntando hacia adentro. golpe=1: inclinada (cuando pasa un separador)."""
    piv_u, piv_v = 0.0, 23.6
    ang = math.radians(-13 if golpe else 0)
    du, dv = U - piv_u, V - piv_v
    lu = du * math.cos(ang) - dv * math.sin(ang)
    lv = du * math.sin(ang) + dv * math.cos(ang)
    px = 1.0 / S
    out = capa(U.shape)

    def gota(lu, lv, crece):
        # cabeza redonda arriba y punta hacia abajo
        cab = 2.25 + crece - np.hypot(lu, lv + 0.2)
        y = -lv  # hacia abajo positivo
        ancho = np.where(y > 0, (2.25 + crece) * (1 - y / (6.2 + crece)), 9)
        tri = np.minimum(ancho - np.abs(lu), (6.2 + crece) - y)
        return np.maximum(cab, np.where(y > 0, tri, -9))

    pintar(out, np.clip(1 - np.maximum(-gota(lu + 0.25, lv + 0.35, 0.45), 0) / 0.8, 0, 1) * 0.5,
           (0.05, 0, 0.08))
    pintar(out, suave(gota(lu, lv, 0.42), px), CONTORNO)
    cuerpo = gota(lu, lv, 0.0)
    g = np.clip((lv + 6) / 8.5, 0, 1)[..., None]
    col = np.asarray((0.85, 0.08, 0.9)) * (1 - g) + np.asarray((1.0, 0.5, 1.0)) * g
    pintar(out, suave(cuerpo, px), col)
    # brillo y estrella
    pintar(out, suave(0.8 - np.hypot(lu + 0.75, lv - 0.75), px), (1, 1, 1), 0.75)
    est = estrella(lu, lv + 0.2, 1.15)
    pintar(out, suave(est, px), (1.0, 0.95, 0.6))
    return out


def estrella(u, v, tam):
    """Estrella de 4 puntas (valor > 0 dentro)."""
    au, av = np.abs(u), np.abs(v)
    return tam - (np.sqrt(au) + np.sqrt(av)) ** 2 * 0.9


def centro(U, V, LOGO, fase=0.0, pop=-1):
    """Placa del centro + logo FP animado.
    fase: 0..1 del bucle (flota, respira, se inclina, brillo diagonal, destellos).
    pop:  -1 normal; 0..N_POP-1 = salto al ganar (crece, destello blanco)."""
    px = 1.0 / S
    r = np.hypot(U, V)
    out = capa(U.shape)
    w = 2 * math.pi * fase
    if pop >= 0:
        curva = [1.1, 1.2, 1.27, 1.24, 1.16, 1.09, 1.04, 1.0]
        flash = [0.42, 0.3, 0.2, 0.12, 0.06, 0.02, 0.0, 0.0]
        esc, blanco = curva[pop], flash[pop]
        bob, giro_l, brillo_glow = 0.0, 0.0, 1.0
    else:
        esc = 1 + 0.045 * math.sin(w)
        blanco = 0.0
        bob = 0.32 * math.sin(w + math.pi / 2)
        giro_l = 3.0 * math.sin(w)
        brillo_glow = 0.55 + 0.35 * (0.5 + 0.5 * math.sin(w))
    rp = R_CENTRO * (1 + 0.35 * (esc - 1))
    # halo rosa que late
    halo = np.clip(1 - (r - rp) / 2.3, 0, 1) ** 2 * (r > rp - 0.2) * brillo_glow
    pintar(out, halo, MAGENTA, 0.85)
    # anillo y placa
    pintar(out, suave(rp + 0.85 - r, px), CONTORNO)
    anillo_t = np.clip((r - rp) / 0.85, 0, 1)
    col_anillo = np.asarray((1.0, 0.55, 1.0)) * (1 - anillo_t[..., None]) + np.asarray((0.75, 0.1, 0.85)) * anillo_t[..., None]
    pintar(out, suave(rp + 0.7 - r, px) * suave(r - rp + 0.05, px), col_anillo)
    tp = np.clip(r / rp, 0, 1)[..., None]
    col_placa = np.asarray((0.36, 0.02, 0.5)) * (1 - tp) + np.asarray(MORADO_OSC) * tp
    pintar(out, suave(rp - r, px), col_placa)
    # brillo de vidrio en la placa
    pintar(out, suave(rp * 0.82 - np.hypot(U + 0.9, V - 1.6), px) * np.clip((V - 0.3) / 4, 0, 1), (1, 1, 1), 0.12)
    # destellos alrededor del logo (como los cuadritos brillantes del logo)
    puntos = [(-4.6, 3.6, 0.0), (4.9, 3.2, 0.33), (4.2, -3.9, 0.6), (-4.8, -3.4, 0.82), (0.2, 5.4, 0.48)]
    for (su, sv, desfase) in puntos:
        if pop >= 0:
            k = (pop + 1) / N_POP
            tam = 1.25 * math.sin(math.pi * min(1.0, k * 1.2)) + 0.05
            su, sv = su * (1 + 0.25 * k), sv * (1 + 0.25 * k)
        else:
            k = (fase + desfase) % 1.0
            tam = max(0.0, math.sin(math.pi * k / 0.45)) * 0.95 if k < 0.45 else 0.0
        if tam > 0.05:
            pintar(out, suave(estrella(U - su, V - sv, tam), px), (1.0, 0.97, 0.75))
    # logo
    alto_logo = 8.3 * esc
    escl = LOGO.shape[0] / alto_logo
    ang = math.radians(giro_l)
    du, dv = U, V - bob - 0.15
    lu = du * math.cos(ang) - dv * math.sin(ang)
    lv = du * math.sin(ang) + dv * math.cos(ang)
    X = LOGO.shape[1] / 2 + lu * escl
    Y = LOGO.shape[0] / 2 - lv * escl
    # sombra del logo
    som = muestrear(LOGO, X - 0.35 * escl, Y - 0.45 * escl)[..., 3]
    pintar(out, som, (0.05, 0, 0.08), 0.55)
    lg = muestrear(LOGO, X, Y)
    # brillo diagonal que recorre el logo (primera mitad del bucle)
    if pop < 0 and fase < 0.5:
        pos = -9 + 18 * (fase / 0.5)
        banda = np.exp(-(((lu + lv * 0.6) - pos) / 0.9) ** 2) * 0.75
        lg[..., :3] = lg[..., :3] + (lg[..., 3] * banda)[..., None] * (1 - lg[..., :3])
    if blanco > 0:
        lg[..., :3] = lg[..., :3] + lg[..., 3:4] * blanco * (1 - lg[..., :3])
    return encima(out, lg)


def relleno(U, V, p):
    """Mancha de color que nace en el gajo de arriba y cubre toda la ruleta (se tine)."""
    r, th = polar(U, V)
    px = 1.0 / S
    d = np.abs(dang(th, 0.0))
    ola = 5.0 * np.sin(r * 0.85 - p * 9) + 3.0 * np.sin(r * 2.1 + p * 5)
    alcance = 18 + p * 175 + ola * (1 - p ** 3)
    borde_ang = np.radians(np.clip(alcance - d, -30, 90))
    dist = r * np.sin(borde_ang)
    m = suave(dist, px * 1.5) * suave(R_DISCO + 0.05 - r, px)
    if p >= 1:
        m = suave(R_DISCO + 0.05 - r, px)
    t = np.clip(r / R_DISCO, 0, 1)
    v = 0.86 + 0.14 * t ** 1.3
    v = v * (1 - 0.15 * suave(r - (R_DISCO - 1.2), 1.6))
    espuma = suave(1.3 - dist, 0.6) * (p < 1)
    v = np.clip(v + 0.14 * espuma, 0, 1)
    out = capa(U.shape)
    out[..., :3] = (v * m)[..., None]
    out[..., 3] = m
    return out


def brillo(U, V, k):
    """Destello blanco que cruza el disco de color (no se tine)."""
    r = np.hypot(U, V)
    px = 1.0 / S
    pos = -26 + 52 * (k + 0.5) / N_BRILLO
    eje = U * 0.75 + V * 0.66
    a = np.exp(-((eje - pos) / 2.6) ** 2) * 0.5 + np.exp(-((eje - pos + 3.6) / 0.7) ** 2) * 0.35
    a = a * suave(R_DISCO - 0.4 - r, px)
    out = capa(U.shape)
    out[..., :3] = a[..., None]
    out[..., 3] = a
    return out


# ------------------------------------------------------------------ composicion completa
def tenir(c, rgb):
    out = c.copy()
    out[..., :3] *= np.asarray(hexf(rgb), np.float32)
    return out


def cuadro_completo(U, V, R, cuadro=0, fase=0.0, aro_m=0, golpe=0, rell=None, color_rell=None,
                    pop=-1, brillo_k=-1, con_gajos=True):
    out = capa(U.shape)
    if con_gajos:
        for s in range(8):
            i = (12 * s + cuadro) % CUADROS
            out = encima(out, tenir(gajo(U, V, i), COLORES[s]))
            out = encima(out, marca(U, V, i, R['INT']))
    if rell is not None:
        out = encima(out, tenir(relleno(U, V, rell), color_rell))
    if brillo_k >= 0:
        out = encima(out, brillo(U, V, brillo_k))
    out = encima(out, aro(U, V, aro_m))
    out = encima(out, centro(U, V, R['LOGO'], fase, pop))
    out = encima(out, flecha(U, V, golpe))
    return out


# ------------------------------------------------------------------ piezas (Java)
class Fuente:
    def __init__(self, carpeta_tex):
        self.proveedores = []
        self.siguiente = 0xE000
        self.carpeta = carpeta_tex
        self.n = 0
        os.makedirs(carpeta_tex, exist_ok=True)
        # espacios: F8F0+k = +2^k, F8E0+k = -2^k
        adv = {}
        for k in range(9):
            adv[chr(0xF8F0 + k)] = 2 ** k
            adv[chr(0xF8E0 + k)] = -(2 ** k)
        self.proveedores.append({"type": "space", "advances": adv})

    def espacio(self, delta):
        s = []
        signo = 1 if delta > 0 else -1
        resto = abs(delta)
        for k in range(8, -1, -1):
            while resto >= 2 ** k:
                s.append(chr((0xF8F0 if signo > 0 else 0xF8E0) + k))
                resto -= 2 ** k
        return ''.join(s)

    def sprite(self, nombre, func, caja):
        """caja = (u0, u1, v0, v1) en unidades respecto al centro de la ruleta.
        Devuelve el texto que dibuja el sprite y regresa el cursor a 0."""
        u0, u1, v0, v1 = caja
        gx0, gx1 = u0, u1
        gy0, gy1 = v0 + CY, v1 + CY
        x_ini = math.floor(gx0)
        top_ini = math.ceil(gy1)
        assert top_ini <= ALTO_U, (nombre, top_ini)
        texto = []
        cursor = 0
        n_piezas = 0
        top = top_ini
        while top > gy0:
            x = x_ini
            while x < gx1:
                w_px = min(TILE, math.ceil((gx1 - x) * S) + 1)
                img = render_pieza(func, x, top, w_px)
                if img is not None:
                    c = chr(self.siguiente)
                    self.siguiente += 1
                    archivo = f"{nombre}_{n_piezas}.png"
                    img.save(os.path.join(self.carpeta, archivo), optimize=True)
                    self.proveedores.append({"type": "bitmap", "file": f"funkypunky:font/ruleta_hd/{archivo}",
                                             "ascent": int(top), "height": ALTO_U, "chars": [c]})
                    texto.append(self.espacio(x - cursor))
                    texto.append(c)
                    cursor = x + int(0.5 + w_px * ALTO_U / TILE) + 1
                    n_piezas += 1
                    self.n += 1
                x += ALTO_U
            top -= ALTO_U
        texto.append(self.espacio(0 - cursor))
        return ''.join(texto)


def render_pieza(func, x, top, w_px):
    paso = 1.0 / (S * SS)
    gx = x + (np.arange(w_px * SS) + 0.5) * paso
    gy = top - (np.arange(TILE * SS) + 0.5) * paso
    GX, GY = np.meshgrid(gx, gy)
    rgba = func(GX.astype(np.float32), (GY - CY).astype(np.float32))
    rgba = rgba.reshape(TILE, SS, w_px, SS, 4).mean(axis=(1, 3))
    a = rgba[..., 3]
    if a.max() < 1.5 / 255:
        return None
    rgb = np.where(a[..., None] > 1e-6, rgba[..., :3] / np.maximum(a[..., None], 1e-6), 0)
    out = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)[..., None]], -1)
    out = (out * 255 + 0.5).astype(np.uint8)
    # Minecraft calcula el ancho de la letra hasta la ultima columna con algo de alfa:
    # un pixel casi invisible en la ultima columna fija el ancho (y el avance) de cada pieza.
    if out[:, -1, 3].max() == 0:
        out[0, -1, 3] = 1
    return Image.fromarray(out, 'RGBA')


def caja_gajo(i):
    """Caja (unidades) que encierra el gajo i."""
    angs = np.radians(np.linspace(3.75 * i, 3.75 * i + 45, 40))
    us = np.concatenate([[0], R_DISCO * np.sin(angs)])
    vs = np.concatenate([[0], R_DISCO * np.cos(angs)])
    m = 0.3
    return (us.min() - m, us.max() + m, vs.min() - m, vs.max() + m)


def caja_marca(i):
    thc = math.radians(3.75 * i + 22.5)
    cu, cv = 12.9 * math.sin(thc), 12.9 * math.cos(thc)
    return (cu - 3.3, cu + 3.3, cv - 3.3, cv + 3.3)


# ------------------------------------------------------------------ programa
def main():
    ruta_logo, salida = sys.argv[1], sys.argv[2]
    R = {'LOGO': preparar_logo(ruta_logo), 'INT': preparar_interrogacion()}
    solo_vista = os.environ.get('SOLO_VISTA') == '1'
    os.makedirs(salida, exist_ok=True)

    # ---- vista previa rapida de los estados principales
    def vista(nombre, escala=1.0, **kw):
        n = 700
        lado = 2 * 27.0
        g = (np.arange(n * 2) + 0.5) / (n * 2) * lado - lado / 2
        U, V = np.meshgrid(g, -g)
        U, V = U / escala, V / escala
        c = cuadro_completo(U.astype(np.float32), V.astype(np.float32), R, **kw)
        c = c.reshape(n, 2, n, 2, 4).mean(axis=(1, 3))
        a = c[..., 3:4]
        rgb = np.where(a > 1e-6, c[..., :3] / np.maximum(a, 1e-6), 0)
        im = Image.fromarray((np.concatenate([np.clip(rgb, 0, 1), a], -1) * 255 + 0.5).astype(np.uint8))
        return im

    if solo_vista:
        estados = [dict(cuadro=0), dict(cuadro=40, fase=0.25, aro_m=1, golpe=1),
                   dict(cuadro=90, rell=0.35, color_rell=COLORES[1], aro_m=2),
                   dict(cuadro=90, rell=1.0, color_rell=COLORES[1], aro_m=2, pop=2, con_gajos=False, brillo_k=2)]
        fondo = Image.new('RGBA', (700 * len(estados), 700), (58, 92, 64, 255))
        for k, e in enumerate(estados):
            fondo.alpha_composite(vista('v', **e), (700 * k, 0))
        fondo.save(os.path.join(salida, 'vista.png'))
        return

    tex = os.path.join(salida, 'java', 'assets', 'funkypunky', 'textures', 'font', 'ruleta_hd')
    F = Fuente(tex)
    sprites = {}

    def lote(clave, n, func_de_k, caja_de_k):
        sprites[clave] = []
        for k in range(n):
            sprites[clave].append(F.sprite(f"{clave.lower()}_{k:02d}", func_de_k(k), caja_de_k(k)))
        print(clave, n, 'listos; piezas totales', F.n, flush=True)

    lote('GAJO', CUADROS, lambda i: (lambda U, V: gajo(U, V, i)), caja_gajo)
    lote('MARCA', CUADROS, lambda i: (lambda U, V: marca(U, V, i, R['INT'])), caja_marca)
    caja_aro = (-R_ARO_OUT - 1.2, R_ARO_OUT + 1.2, -R_ARO_OUT - 1.2, R_ARO_OUT + 1.2)
    lote('ARO', 3, lambda m: (lambda U, V: aro(U, V, m)), lambda m: caja_aro)
    lote('FLECHA', 2, lambda g: (lambda U, V: flecha(U, V, g)), lambda g: (-4.3, 4.3, 15.6, 26.3))
    caja_centro = (-10.2, 10.2, -10.2, 10.2)
    lote('LOGO', N_LOGO, lambda k: (lambda U, V: centro(U, V, R['LOGO'], k / N_LOGO)), lambda k: caja_centro)
    lote('LOGO_POP', N_POP, lambda k: (lambda U, V: centro(U, V, R['LOGO'], 0.0, k)), lambda k: caja_centro)
    caja_disco = (-R_DISCO - 0.3, R_DISCO + 0.3, -R_DISCO - 0.3, R_DISCO + 0.3)

    def p_rell(k):
        x = (k + 1) / N_RELLENO
        return 1.0 if k == N_RELLENO - 1 else 0.5 - 0.5 * math.cos(math.pi * x)

    lote('RELLENO', N_RELLENO, lambda k: (lambda U, V: relleno(U, V, p_rell(k))), lambda k: caja_disco)
    lote('BRILLO', N_BRILLO, lambda k: (lambda U, V: brillo(U, V, k)), lambda k: caja_disco)

    def entrada(k):
        e = ESCALAS_ENTRADA[k]
        return lambda U, V: cuadro_completo(U / e, V / e, R)

    def caja_entrada(k):
        e = ESCALAS_ENTRADA[k]
        return (-(R_ARO_OUT + 1.3) * e, (R_ARO_OUT + 1.3) * e, -(R_ARO_OUT + 1.3) * e, 26.3 * e)

    lote('ENTRADA', len(ESCALAS_ENTRADA), entrada, caja_entrada)

    # ---- fuente de Java
    carpeta_fuente = os.path.join(salida, 'java', 'assets', 'funkypunky', 'font')
    os.makedirs(carpeta_fuente, exist_ok=True)
    with open(os.path.join(carpeta_fuente, 'ruleta.json'), 'w', encoding='utf-8') as f:
        json.dump({"providers": F.proveedores}, f, ensure_ascii=True, indent=1)

    # ---- Bedrock: una letra por cuadro en glyph_E2.png (16x16 celdas de 256 px)
    be = {}
    celdas = []

    def be_add(clave, **kw):
        celdas.append(kw)
        be.setdefault(clave, []).append(0xE200 + len(celdas) - 1)

    for f in range(CUADROS):
        be_add('BE_GIRO', cuadro=f, aro_m=f % 2)
    for k, e in enumerate(ESCALAS_ENTRADA):
        be_add('BE_ENTRADA', escala=e)
    pasos_be = [1, 3, 5, 7, 8, 9]  # cuadros del relleno de Java que usa Bedrock
    for s in range(8):
        f = (96 - 12 * s - 6) % 96
        for k in pasos_be:
            be_add(f'BE_RELLENO_{s}', cuadro=f, rell=p_rell(k), color_rell=COLORES[s], aro_m=2)
        be_add(f'BE_FINAL_{s}', rell=1.0, color_rell=COLORES[s], aro_m=2, con_gajos=False)
        be_add(f'BE_FINAL_{s}', rell=1.0, color_rell=COLORES[s], aro_m=2, con_gajos=False, pop=2)
    print('Bedrock: celdas', len(celdas), flush=True)
    assert len(celdas) <= 256
    pagina = Image.new('RGBA', (4096, 4096), (0, 0, 0, 0))
    lado = 2 * 27.6   # unidades que caben en la celda (centro de la ruleta en el centro)
    n = 256
    g = (np.arange(n * SS) + 0.5) / (n * SS) * lado - lado / 2
    GU, GV = np.meshgrid(g, -g)
    GV = GV + 2.4   # sube un poco el encuadre: la flecha sobresale arriba
    for idx, kw in enumerate(celdas):
        e = kw.pop('escala', 1.0)
        c = cuadro_completo((GU / e).astype(np.float32), (GV / e).astype(np.float32), R, **kw)
        c = c.reshape(n, SS, n, SS, 4).mean(axis=(1, 3))
        a = c[..., 3:4]
        rgb = np.where(a > 1e-6, c[..., :3] / np.maximum(a, 1e-6), 0)
        arr = (np.concatenate([np.clip(rgb, 0, 1), a], -1) * 255 + 0.5).astype(np.uint8)
        arr[0, 0, 3] = max(arr[0, 0, 3], 1)    # ancho fijo en Bedrock (no recorta la celda)
        arr[0, -1, 3] = max(arr[0, -1, 3], 1)
        pagina.paste(Image.fromarray(arr), ((idx % 16) * 256, (idx // 16) * 256))
    os.makedirs(os.path.join(salida, 'bedrock', 'font'), exist_ok=True)
    pagina.save(os.path.join(salida, 'bedrock', 'font', 'glyph_E2.png'), optimize=True)

    # ---- Sprites.java
    def jstr(s):
        return '"' + ''.join(f'\\u{ord(ch):04X}' for ch in s) + '"'

    L = ["package lat.funkypunky.ruleta;", "",
         "/** GENERADO por generar_ruleta_hd.py: no editar a mano (pack 4, ruleta HD). */",
         "final class Sprites {", "    private Sprites() {", "    }", ""]
    L.append("    static final int[] COLORES = {" + ", ".join(f"0x{c:06X}" for c in COLORES) + "};")
    for clave, lista in sprites.items():
        L.append(f"    static final String[] {clave} = {{")
        for s in lista:
            L.append(f"        {jstr(s)},")
        L.append("    };")
    for clave in ['BE_GIRO', 'BE_ENTRADA']:
        L.append(f"    static final String[] {clave} = {{" + ", ".join(jstr(chr(c)) for c in be[clave]) + "};")
    for clave in ['BE_RELLENO', 'BE_FINAL']:
        L.append(f"    static final String[][] {clave} = {{")
        for s in range(8):
            L.append("        {" + ", ".join(jstr(chr(c)) for c in be[f'{clave}_{s}']) + "},")
        L.append("    };")
    L.append("}")
    with open(os.path.join(salida, 'Sprites.java'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print('Listo. Piezas Java:', F.n, flush=True)


if __name__ == '__main__':
    main()
