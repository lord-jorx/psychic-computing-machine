Verifica el manuscrito ítem a ítem contra la guía de reporte que corresponda (PRISMA 2020, STROBE, CONSORT, TRIPOD+AI, etc.) y genera el checklist como material suplementario.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>` y, si no es obvio por el diseño del estudio, qué guía aplicar (ver la tabla de PLAN.md §8).

## Pasos

1. Determina la guía correcta por el diseño del estudio (declarado en `protocol.md`):
   - Revisión sistemática/metaanálisis → **PRISMA 2020** (27 ítems + diagrama de flujo)
   - Revisión de alcance → **PRISMA-ScR** (20 ítems)
   - Observacional (cohorte, casos-control) → **STROBE** (22 ítems)
   - Ensayo aleatorizado → **CONSORT 2025**
   - Modelo predictivo → **TRIPOD+AI**
   - Innovación quirúrgica → clasifica además la etapa del marco **IDEAL** (0-4) y comprueba que las conclusiones no excedan lo que esa etapa permite afirmar (una etapa 2a no sostiene una conclusión de eficacia comparativa).

2. Para cada ítem de la guía, busca en `main.tex` dónde se cumple. Si no lo encuentras, dilo explícitamente — no asumas que "probablemente está" en algún sitio.

3. Para PRISMA específicamente, comprueba que el diagrama de flujo usado en el manuscrito es el generado por `python -m jordilabor prisma`, no uno redibujado a mano con números distintos.

4. Escribe el checklist relleno en `<workspace>/manuscript/prisma_checklist.md` (o el nombre que corresponda a la guía usada), con una columna "ubicación" que apunte a la sección/página del manuscrito.

5. Antes de terminar, corre los chequeos de integridad — no des el manuscrito por conforme si estos fallan:
   ```bash
   python -m jordilabor integrity resolve-citations --bib <workspace>/manuscript/references.bib
   python -m jordilabor integrity check-provenance   --workspace <workspace> --manuscript <workspace>/manuscript/main.tex
   ```

6. Añade (o verifica que ya existe) la declaración de uso de IA en Métodos: qué modelos se usaron, en qué etapas (cribado, extracción — nunca en interpretación/discusión sin supervisión), y quién verificó cada etapa. El ICMJE exige esta declaración explícita.
