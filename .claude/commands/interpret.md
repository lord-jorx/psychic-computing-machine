Interpreta los resultados del metaanálisis y prepara la puerta G4, antes de redactar la discusión.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>` y el/los `--outcome` ya analizados en R.

## Pasos

1. Lee `<workspace>/analysis/results_<outcome>.json` para cada desenlace analizado. Fíjate en: `estimate`/`estimate_exp`, `ci_lb`/`ci_ub`, `i2`, `q_pvalue`, `egger_p_value`, `k`.

2. Aplica el marco GRADE mentalmente (o formalízalo si el usuario lo pide) sobre cinco dominios que bajan la certeza: riesgo de sesgo (usa lo que registraste en `bias add`), inconsistencia (I² alto sin explicación = baja certeza), evidencia indirecta, imprecisión (IC ancho, pocos eventos/estudios) y sesgo de publicación (Egger significativo, asimetría del funnel plot, o ensayos en ClinicalTrials.gov sin publicación emparejada).

3. Antes de escribir una sola frase de conclusión, dile al usuario explícitamente:
   - el tamaño del efecto y su IC, en lenguaje clínico (no solo el número),
   - el nivel de certeza GRADE resultante y por qué,
   - si I² es alto (>50-75% orientativo, no umbral rígido), si tiene sentido interpretar el efecto combinado en absoluto o si hace falta explicar la heterogeneidad en vez de dar una cifra pooled como si fuera sólida,
   - si `k` es bajo (<5-10 estudios), advierte que ni Egger ni el funnel plot son fiables para detectar sesgo de publicación con tan pocos estudios.

4. **No dejes que la conclusión exceda lo que soportan los datos.** Es el error más común y el motivo de rechazo más frecuente en revisión por pares quirúrgica: un I²=85% con "el tratamiento reduce las complicaciones" sin matizar heterogeneidad es sobreinterpretación. Señálalo aunque el usuario no pregunte.

5. Cuando el usuario esté de acuerdo con la interpretación, ayúdale a redactar la sección de Discusión con esa interpretación exacta (ver `.claude/commands/writeup.md` para el resto del manuscrito), y aprueba:
   ```bash
   python -m freemdlabor gate approve G4 <workspace>/analysis/results_<outcome>.json --workspace <workspace> --by "<nombre>"
   ```
   (repite por cada desenlace principal si aplica, o aprueba sobre el fichero de resultados del desenlace primario si es el que gobierna la conclusión central).
