# freeMDlabor

Herramientas deterministas + un router LLM barato para producir revisiones
sistemáticas, metaanálisis y análisis secundarios en medicina y cirugía,
orquestadas desde Claude Code (Vía A del plan). Ver [`PLAN.md`](PLAN.md)
para el razonamiento completo; este README es solo el arranque práctico.

No es un framework multiagente. La orquestación eres tú, dentro de Claude
Code, invocando estos comandos o los slash commands de `.claude/commands/`.
Lo único "autónomo" es el cribado y la extracción en lote sobre literatura
pública, con un tope de coste explícito (§ más abajo).

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # rellena al menos una clave gratuita (Gemini o Groq)
cp config.example.yaml config.yaml   # ajusta el enrutado por rol si quieres
```

Para el metaanálisis necesitas R con `metafor` y `jsonlite`:

```r
install.packages(c("metafor", "jsonlite"))
```

## Arranque de una revisión

```bash
python -m freemdlabor init results/2026-lap-vs-open-appy
```

Esto crea `protocol.md` (plantilla PICO), `review.sqlite`, y las carpetas
`search/ screening/ extraction/ analysis/ manuscript/ gates/`.

**Edita `protocol.md` a mano** (o con ayuda de Claude Code — ver
`.claude/commands/protocol.md`). No sigas hasta que esté completo: todo el
cribado se enruta contra este fichero.

### G1 — puerta de protocolo

```bash
python -m freemdlabor gate approve G1 $W/protocol.md --workspace $W --by "tu nombre"
```

Sin esto, nada del pipeline avanza (aunque nada te lo impide técnicamente
todavía en esta versión — la disciplina de puertas la ejercita `gate status`
y las convenciones del proyecto en `CLAUDE.md`, no un candado de sistema
de ficheros).

## Pipeline

```bash
W=results/2026-lap-vs-open-appy

# 1. Búsqueda multibase (sin claves, salvo NCBI_API_KEY opcional)
python -m freemdlabor search --workspace $W --source pubmed        --query "laparoscopic appendectomy AND open appendectomy AND randomized"
python -m freemdlabor search --workspace $W --source europepmc     --query "laparoscopic appendectomy open appendectomy"
python -m freemdlabor search --workspace $W --source clinicaltrials --query "appendectomy laparoscopic"
python -m freemdlabor search --workspace $W --source openalex      --query "laparoscopic vs open appendectomy"

# 2. Deduplicación determinista (DOI/PMID exacto + título difuso)
python -m freemdlabor dedup --workspace $W

# 3. Cribado doble pase (requiere GOOGLE_API_KEY o GROQ_API_KEY)
python -m freemdlabor screen title-abstract --workspace $W --pass pass_a
python -m freemdlabor screen title-abstract --workspace $W --pass pass_b
python -m freemdlabor screen kappa          --workspace $W
python -m freemdlabor screen conflicts      --workspace $W   # -> screening/conflicts_title_abstract.csv

# G2: resuelve cada conflicto a mano
python -m freemdlabor screen resolve --workspace $W --record-id 42 --decision include --by "tu nombre"
python -m freemdlabor gate approve G2 $W/screening/conflicts_title_abstract.csv --workspace $W --by "tu nombre"

# 4. Elegibilidad a texto completo (uno a uno; el texto lo consigues tú o
#    vía Europe PMC OA — full_text_url en el registro)
python -m freemdlabor screen full-text --workspace $W --record-id 42 --full-text-file study42.txt

# 5. Extracción a esquema fijo — edita extraction/schema.json ANTES de esto
python -m freemdlabor extract run    --workspace $W --record-id 42 --full-text-file study42.txt
python -m freemdlabor extract export --workspace $W    # -> extraction/studies.csv

# G3: verifica el 20% de las celdas contra el PDF original
python -m freemdlabor extract verify --workspace $W --record-id 42 --field n_intervention --by "tu nombre"
python -m freemdlabor gate approve G3 $W/extraction/studies.csv --workspace $W --by "tu nombre"

# 6. Recuento y diagrama PRISMA 2020 (siempre desde la base, nunca a mano)
python -m freemdlabor prisma --workspace $W --title "Lap vs open appendectomy"

# 7. Metaanálisis en R
Rscript analysis/meta_analysis.R \
  --input=$W/extraction/studies.csv \
  --outcome=surgical_site_infection \
  --measure=OR \
  --out-dir=$W/analysis

# 8. Redacción del manuscrito (main.tex) — ver .claude/commands/writeup.md
#    Cada cifra que escribas lleva un \provenance{claim_id} y un registro:
python -m freemdlabor integrity add-provenance --workspace $W \
  --claim-id ssi_or --value "OR 0.62 (95% CI 0.44-0.87)" \
  --source-table analysis --source-ref "results_surgical_site_infection.json:estimate_exp"

# 9. Integridad — falla duro si algo no resuelve. Ejecuta ANTES de compilar.
python -m freemdlabor integrity resolve-citations --bib $W/manuscript/references.bib
python -m freemdlabor integrity check-provenance   --workspace $W --manuscript $W/manuscript/main.tex

# G4/G5: interpretación y firma — puertas de conversación, no de script.
python -m freemdlabor gate approve G5 $W/manuscript/main.tex --workspace $W --by "tu nombre"
```

## Coste y cuota

Cribado y extracción pasan por `providers.py`, que resuelve cada *rol* según
`config.yaml` — no hay una única "cuenta" que se agote de golpe. Por
defecto, `screening` y `extraction` van a la capa gratuita de Gemini;
`judgment` (protocolo, interpretación, discusión) está marcado
`provider: interactive` a propósito — **no se puede llamar desde código**,
porque ahí es donde usas tu sesión de Claude Code de verdad. Ver PLAN.md §3.

## Qué NO hace este código

Ver PLAN.md §12. En corto: no diseña estudios prospectivos, no sustituye tu
registro en PROSPERO ni la aprobación del CEIm, no firma nada por ti, y no
debe tocar datos identificables de pacientes en ningún rol de capa
gratuita — `providers.py` lo impide por diseño
(`data_sensitivity="restricted"` + `tier: free` → excepción dura).

## Tests

```bash
pytest tests/
```
