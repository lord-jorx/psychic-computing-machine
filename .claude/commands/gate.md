Muestra el estado de las cinco puertas humanas y, si el usuario lo pide explícitamente en este turno, aprueba o rechaza una.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>` y, opcionalmente, `gate=G1..G5` si el usuario ya pidió actuar sobre una puerta concreta.

## Pasos

1. Muestra el estado actual:
   ```bash
   python -m freemdlabor gate status --workspace <workspace>
   ```

2. Si el usuario no pidió aprobar nada, para aquí y limítate a explicarle qué falta para cada puerta pendiente (usa las descripciones de PLAN.md §9).

3. **Nunca llames a `gate approve` por iniciativa propia.** Solo hazlo cuando el usuario, en esta conversación, haya dado una aprobación explícita y haya dicho con qué nombre firmar (`--by`). Si no lo ha dicho, pregúntaselo — no uses "claude" ni tu propio nombre de agente como `--by`.

4. Para aprobar:
   ```bash
   python -m freemdlabor gate approve <G1..G5> <ruta_del_artefacto> --workspace <workspace> --by "<nombre>" [--notes "..."]
   ```
   Para rechazar explícitamente (registra el intento y por qué, en vez de dejarlo simplemente pendiente):
   ```bash
   python -m freemdlabor gate approve <G1..G5> <ruta_del_artefacto> --workspace <workspace> --by "<nombre>" --reject --notes "<motivo>"
   ```

5. Si el hash del artefacto cambió desde la última aprobación (el comando `gate status`/`check_gate_or_fail` lo detecta), avisa de que la puerta quedó invalidada por un cambio posterior y hay que re-aprobarla — no lo ignores ni lo fuerces.
