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

# Mascotas (BetterModel) sin pasar por el servidor

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
