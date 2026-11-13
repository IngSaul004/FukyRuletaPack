# Herramientas de la ruleta HD (pack 4)

- `generar_ruleta_hd.py` dibuja la ruleta y genera: fuente de Java `funkypunky:ruleta` (piezas de 256 px),
  `glyph_E2.png` de Bedrock y `Sprites.java` (va en el plugin FunkyRuleta, no se edita a mano).
- `simular.py` arma los cuadros como lo hace Minecraft (avances, ascent, espacios, tinte) para revisar
  uniones y hacer la vista previa.
- `logo_fp.png` es el logo del centro.

```
python3 -I generar_ruleta_hd.py logo_fp.png salida      # ~11 min
python3 -I simular.py salida 8 cuadros                    # vista previa cuadro por cuadro
```
Si cambias colores, tamaños o numero de cuadros: vuelve a generar, copia `Sprites.java` al plugin,
vuelve a armar el pack de Java (borrando `assets/funkypunky/textures/font/ruleta_hd` antes) y el mcpack,
y sube la version del `manifest.json` de Bedrock.

# Packs separados + ForcePack (desde el 13-nov)

El pack ya no es uno solo. Cada carpeta de `packs/` es un pack aparte y ForcePack los manda juntos
(Minecraft Java 1.20.3+ acepta varios packs a la vez):

| Carpeta | Contenido | Zip que arma la Action |
| --- | --- | --- |
| `packs/base/` | TAB, panel de AuthMe, panorama, ruleta HD | `salida/FunkyPunky-Base.zip` |
| `packs/mascotas/` | modelos de BetterModel | `salida/FunkyPunky-Mascotas.zip` |
| `packs/armaduras/` | (vacío por ahora) | `salida/FunkyPunky-Armaduras.zip` |

Los packs **no comparten archivos** (cada uno tiene su namespace), así que el orden en que los cargue
el jugador no importa. No meter en un pack archivos que ya tiene otro.

## Agregar una mascota (sin reiniciar)

1. Sube el `.bbmodel` a `mascotas/` (nombre del archivo = id del modelo; animaciones `idle`, `hop`, `hurt`).
2. Espera la palomita verde de la Action **Armar resource packs**: genera las piezas, revisa que no falte
   ningún modelo ni textura, arma `salida/FunkyPunky-Mascotas.zip` y lo sube. La SHA-1 sale en el resumen.
3. En el servidor: el mismo `.bbmodel` en `plugins/BetterModel/models/`, luego
   `bettermodel reload`, `forcepack reload` y la sección nueva en el `config.yml` de FunkyPets + `pets recargar`.
   (GitHub puede tardar ~5 min en dar el zip nuevo: si los jugadores ven la mascota invisible, `forcepack reload` otra vez.)

`mascotas/servidor/` guarda fuentes cuyas piezas hizo el servidor (`slime_bunny`): la Action no las regenera.

## Probar en tu PC

```
python3 -I herramientas/armar_packs.py
```
Si encuentra un JSON roto o un modelo/textura que falta, se detiene y no arma ningún zip.

## Cambiar la ruleta, el TAB o el panel

Editar dentro de `packs/base/` (por ejemplo, el generador de la ruleta escribe en
`packs/base/assets/funkypunky/`). Al hacer push, la Action vuelve a armar `FunkyPunky-Base.zip`.

`FunkyPunky-Pack.zip` (raíz) es el pack unido viejo (V3). Se queda como respaldo; no se edita.

# Mascotas (BetterModel) sin pasar por el servidor (histórico)


`bb2bettermodel.py` genera las piezas de BetterModel (items `bettermodel:c/<modelo>_<hueso>`,
modelos y texturas con prefijo `fp_`) igual que BetterModel 3.7.0 del servidor. Verificado contra
el pack que generó el servidor (slime_bunny, blue_wizard, demon_knight: 63 de 63 piezas iguales,
salvo redondeos de 0.000003).

```
python3 -I bb2bettermodel.py salida ../mascotas/appa.bbmodel ...
```
Después: descomprimir `FunkyPunky-Pack.zip`, copiar `salida/assets/bettermodel/` encima (sin pisar),
volver a comprimir, calcular la SHA-1 y cambiar link + SHA-1 en `server.properties`.
El mismo `.bbmodel` (mismo nombre de archivo) tiene que estar en `plugins/BetterModel/models/` del servidor.
Los `.bbmodel` fuente de las mascotas nuevas están en `mascotas/`.
