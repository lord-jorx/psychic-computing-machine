Redacta el manuscrito en LaTeX (IMRaD) a partir de lo que ya está en el workspace — nunca a partir de memoria o de lo que "suena plausible".

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>` y opcionalmente la plantilla (`elsarticle` para Elsevier, `sn-jnl` para Springer/BMC; pregunta si no está claro).

## Pasos

1. Antes de escribir nada, lee: `protocol.md`, `prisma/counts.json`, `extraction/studies.csv`, `analysis/results_*.json`, y las filas de `bias_assessments`. El manuscrito describe lo que hay ahí — no rellenes huecos con supuestos.

2. Estructura IMRaD estándar:
   - **Introducción**: contexto clínico + la brecha que motiva esta revisión (usa lo que se encontró al comprobar duplicidad en el paso de protocolo).
   - **Métodos**: protocolo (con nº de registro PROSPERO si existe), fuentes y estrategia de búsqueda exacta (cópialas de `search/` — no las reescribas de memoria), criterios de elegibilidad, proceso de cribado (menciona el doble pase, el kappa obtenido, cómo se resolvieron conflictos), extracción de datos, herramienta de riesgo de sesgo, método estadístico, y — obligatorio — la declaración de uso de IA (ver `.claude/commands/compliance.md`).
   - **Resultados**: el diagrama de flujo PRISMA (`prisma/flow_diagram.svg`, incrústalo o referencia sus cifras), características de los estudios incluidos (tabla desde `studies.csv`), riesgo de sesgo (tabla/figura desde `bias_assessments.csv`), resultados del metaanálisis (forest/funnel plots, cifras desde `results_*.json`).
   - **Discusión**: usa exactamente la interpretación acordada en `.claude/commands/interpret.md` — no la reescribas más fuerte "para que suene mejor". Incluye limitaciones reales (sin Embase/CENTRAL si aplica, I² alto si aplica, k bajo si aplica).

3. **Cada cifra numérica que escribas necesita su `\provenance{claim_id}`.** Inmediatamente después de escribir una cifra, registra su origen:
   ```bash
   python -m jordilabor integrity add-provenance --workspace <workspace> \
     --claim-id <id_corto_descriptivo> --value "<lo que escribiste>" \
     --source-table analysis --source-ref "results_<outcome>.json:<campo>"
   ```
   (o `--source-table extractions --source-ref <extraction_row_id>` para datos de un estudio individual). No lo dejes para el final — hazlo en el momento, o se te olvidará qué cifra venía de dónde.

4. **Cada referencia bibliográfica** en `references.bib` debe venir de un registro real de tu búsqueda (con DOI) — nunca inventada ni citada de memoria. Si necesitas una referencia que no está en `review.sqlite` (p. ej. una guía clínica de fondo), búscala de verdad (PubMed/Crossref) antes de citarla.

5. Compila y verifica antes de decir que está listo:
   ```bash
   python -m jordilabor integrity resolve-citations --bib <workspace>/manuscript/references.bib
   python -m jordilabor integrity check-provenance   --workspace <workspace> --manuscript <workspace>/manuscript/main.tex
   ```
   Si cualquiera de los dos falla, el manuscrito no está terminado — arréglalo, no lo reportes como "listo con advertencias".

6. No apruebes G5 tú. Preséntale al usuario el manuscrito, el checklist de cumplimiento y los resultados de integridad, y pide su aprobación explícita antes de:
   ```bash
   python -m jordilabor gate approve G5 <workspace>/manuscript/main.tex --workspace <workspace> --by "<nombre>"
   ```
