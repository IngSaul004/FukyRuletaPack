# Pack de armaduras (todavía vacío)

Cuando haya armaduras personalizadas, sus archivos van aquí con la misma forma de un resource pack:

```
packs/armaduras/pack.mcmeta
packs/armaduras/assets/funkypunky/...
```

Mientras esta carpeta no tenga `pack.mcmeta` y `assets/`, `armar_packs.py` la ignora y no se
manda ningún pack vacío. En cuanto los tenga, la Action arma `salida/FunkyPunky-Armaduras.zip`
y solo hay que agregar su link a `urls` de ForcePack.

Reglas:
- Usar el namespace propio `funkypunky:` (nunca reemplazar archivos de `minecraft:` que ya usa otro pack).
- Solo apariencia: la armadura del jugador conserva su protección (regla de Mojang).
- Bedrock necesita su propio pack + mapeo en Geyser (cada textura se hace dos veces).
