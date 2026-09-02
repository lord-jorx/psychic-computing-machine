Evalúa el riesgo de sesgo de los estudios incluidos. Este es un paso de juicio (`role: judgment`) — lo haces tú, leyendo el texto, no un modelo en lote.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>` y, si el usuario ya lo dijo, qué herramienta aplicar. Si no lo dijo, elige según el diseño declarado en `protocol.md`:
- Ensayos aleatorizados → **RoB 2** (dominios: proceso de aleatorización, desviaciones de la intervención, datos de desenlace faltantes, medición del desenlace, selección del resultado reportado)
- Estudios no aleatorizados de intervenciones → **ROBINS-I** (confusión, selección, clasificación de la intervención, desviaciones, datos faltantes, medición, reporte selectivo)
- Estudios de precisión diagnóstica → **QUADAS-2**
- Cohortes/casos-control sin ROBINS-I → **Newcastle-Ottawa Scale (NOS)**

## Pasos

1. Para cada estudio incluido (los que tienen `decision='include'` en `full_text`), lee el texto completo con foco en el dominio que estás evaluando.

2. Para cada dominio, decide el juicio (`low` / `some_concerns` / `high` para RoB2; `low` / `moderate` / `serious` / `critical` para ROBINS-I) y escribe una justificación de 1-3 frases que cite explícitamente lo que en el texto sustenta ese juicio — no un juicio genérico tipo "razonablemente bien reportado".

3. Registra cada dominio:
   ```bash
   python -m freemdlabor bias add --workspace <workspace> --record-id <id> \
     --tool RoB2 --domain "randomization_process" --judgment low \
     --justification "..." --quote "<cita textual del artículo>" --by "claude-code"
   ```
   Si el usuario está revisando contigo en vivo, usa `--by "human:<nombre>"` en vez de `claude-code` para las que él confirme directamente.

4. Cuando termines todos los estudios, exporta:
   ```bash
   python -m freemdlabor bias export --workspace <workspace>
   ```

5. Resume para el usuario: ¿hay algún estudio con riesgo global "alto/crítico" que convenga excluir de un análisis de sensibilidad? Coméntalo antes de pasar al metaanálisis — no lo decidas por tu cuenta.
