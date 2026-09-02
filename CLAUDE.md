# freeMDlabor — instrucciones para Claude Code

Este proyecto produce revisiones sistemáticas, metaanálisis y análisis
secundarios en medicina/cirugía. Tú (Claude Code, con Claude Pro) eres el
orquestador y el responsable de juicio clínico; `freemdlabor/` es el
núcleo determinista y el router LLM barato que hace el trabajo mecánico.
Ver `PLAN.md` para la arquitectura completa y `README.md` para el arranque.

## Reglas que no se negocian

1. **Nunca inventes una cita.** Toda entrada de `references.bib` debe tener
   un DOI que resuelva de verdad. Antes de decir que un manuscrito está
   listo, corre siempre:
   ```
   python -m freemdlabor integrity resolve-citations --bib <manuscript>/references.bib
   ```
   Si falla, el manuscrito no está listo — punto. No "avises y sigas".

2. **Ninguna cifra sin `\provenance{}`.** Cada número que escribas en el
   manuscrito (un OR, un tamaño muestral, un p-valor) necesita una entrada
   `\provenance{claim_id}` en el LaTeX y una fila correspondiente vía
   `python -m freemdlabor integrity add-provenance`. Corre
   `integrity check-provenance` antes de dar por cerrada una sección.

3. **Nunca generes datos de ejemplo dentro del workspace de una revisión
   real** (`results/<review>/...`). Si necesitas un fixture para probar
   algo, créalo en `tests/fixtures/` con un nombre que lo delate
   (`fake_*`), nunca dentro de un workspace de revisión.

4. **`data_sensitivity="restricted"` nunca va a un proveedor `tier: free`.**
   Esto ya lo impone `providers.py` (lanza `DataSensitivityError`), pero
   tampoco lo intentes rodear cambiando `config.yaml` sin pensarlo: datos de
   pacientes (MIMIC, SEER, cualquier extracto de HCE) no van a una capa
   gratuita, fin de la discusión.

5. **El rol `judgment` no se llama por código.** Si ves `provider:
   interactive` en `config.yaml`, ese paso lo haces tú, aquí, en esta
   conversación — protocolo, riesgo de sesgo, interpretación, discusión,
   cumplimiento normativo. `call_llm()` lanzará `InteractiveRoleError` si
   algo intenta invocarlo programáticamente; eso es intencional, no un bug
   que arreglar.

6. **Los recuentos PRISMA nunca se escriben a mano.** Siempre
   `python -m freemdlabor prisma --workspace <W>`. Si un número no cuadra
   con lo que crees que debería ser, el bug está en `review.sqlite`
   (una decisión de cribado mal registrada), no en el generador.

7. **Ninguna puerta humana se aprueba sola.** `gate approve` requiere
   `--by <nombre real>`. Nunca la llames con tu propio nombre de agente ni
   apruebes en nombre del usuario sin que él lo haya dicho explícitamente
   en la conversación.

## Cómo actuar en cada etapa

Los seis pasos de juicio (protocolo, cribado — revisión de conflictos,
extracción — verificación, riesgo de sesgo, interpretación, cumplimiento y
redacción) tienen su propio slash command en `.claude/commands/`. Úsalos
como checklist, no como guion rígido: la idea es que no se te olvide un
paso, no que sigas una plantilla ciegamente.

Para todo lo mecánico (buscar, deduplicar, cribar en lote, extraer en lote,
generar el diagrama PRISMA, correr el metaanálisis), invoca
`python -m freemdlabor ...` o `Rscript analysis/meta_analysis.R` — no
reimplementes esa lógica en la conversación ni la hagas "a mano" citando
de memoria.

## Estructura de un workspace de revisión

```
results/<fecha>_<nombre-revision>/
├── protocol.md              # PICO, criterios, estrategia — congelado tras G1
├── review.sqlite            # fuente única de verdad
├── search/                  # (los raw_json viven dentro de cada record)
├── screening/conflicts_*.csv
├── extraction/schema.json, studies.csv
├── analysis/results_*.json, figures/
├── manuscript/main.tex, references.bib
└── gates/gate_G*.approved
```

## Limitaciones conocidas (decláralas, no las escondas)

- Sin Embase ni Cochrane CENTRAL (de pago, sin API abierta): decláralo como
  limitación explícita en el manuscrito si no hay acceso institucional.
- La detección heurística de "cifra sin provenance" en
  `integrity.check_provenance` es una red de seguridad, no una garantía —
  úsala para saber dónde mirar, no como sustituto de una lectura final.
- El cribado automático no se usa a escala sin calibrar primero: 100
  registros cribados a mano, kappa medido (`screen kappa`), sensibilidad
  ≥ ~0.95 antes de confiar en él para el resto. Ver PLAN.md F2.
