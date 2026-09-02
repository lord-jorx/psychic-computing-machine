# freeMDlabor — Plan de adaptación de `freephdlabor` a investigación médico-quirúrgica

> Estado: **implementado — núcleo determinista de la Vía A (F0-F1 y parte de F2 del §10)**.
> Base auditada: [`ltjed/freephdlabor`](https://github.com/ltjed/freephdlabor) @ `main` (clonado y revisado fichero a fichero).
> Restricción de partida: ejecutable con **cuenta Claude Pro** o con **APIs gratuitas**.
> Versión navegable: https://claude.ai/code/artifact/9d079ec0-5c0c-4b41-b49f-78e43474775d
> Código: [`freemdlabor/`](freemdlabor/) (paquete Python), [`analysis/meta_analysis.R`](analysis/meta_analysis.R), [`.claude/commands/`](.claude/commands/) — ver [`README.md`](README.md) para el arranque.

---

## 1. Veredicto antes del plan

**1.1 · El repo es ~70 % específico de machine learning.**
El núcleo de valor de `freephdlabor` es `RunExperimentTool`, que lanza AI-Scientist-v2 como
subproceso para escribir y ejecutar código de entrenamiento de redes neuronales. En medicina no
hay equivalente: no se ejecuta un ensayo clínico en un contenedor. Ese componente, más las
plantillas ICML/ICLR y la búsqueda centrada en arXiv, se elimina entero. Lo heredable es el
andamiaje: orquestación smolagents, workspace compartido como memoria entre agentes,
compactación de contexto, interrupción en caliente, herramientas de edición de ficheros y el
compilador LaTeX.

**1.2 · Claude Pro no es una API.**
Una suscripción Pro da acceso a Claude a través de los productos de Anthropic (incluido Claude
Code), no una `ANTHROPIC_API_KEY` facturable. `freephdlabor` llama a LiteLLM, que exige esa
clave. Existen atajos técnicos (envolver `claude -p` en un modelo compatible con smolagents),
pero convertir la suscripción en backend de un framework de terceros es frágil y discutible
frente a la política de uso. La consecuencia práctica no es legal sino aritmética: Pro tiene
topes por ventana de 5 h y semanales, y una revisión sistemática consume 4–6 M de tokens. Un
bucle autónomo 24/7 sobre Pro se detiene solo.

**1.3 · La automatización útil no está donde parece.**
El cuello de botella de un paper médico no es escribir: es cribar 3 000 abstracts y extraer 40
variables de 60 artículos sin equivocarse. Eso es trabajo de volumen, ideal para un modelo barato
o gratuito. El juicio clínico —criterios de elegibilidad, interpretación, discusión— es tuyo y
firma contigo. El sistema correcto no es "un PhD autónomo": es **una máquina de cribado y
extracción trazable con un cirujano responsable en el bucle**.

---

## 2. Auditoría del repo: qué se hereda y qué se tira

| Componente | Ruta | Decisión | Motivo |
|---|---|---|---|
| Clase base de agentes | `freephdlabor/agents/base_research_agent.py` | **Mantener** | Workspace, logging y ejecutor propio por agente. Es el activo real del fork. |
| Compactación de contexto | `freephdlabor/agents/context_compaction.py` | **Mantener** | Imprescindible: un cribado largo desborda cualquier ventana. |
| Ejecutor de workspace | `freephdlabor/interpreters/workspace_executor.py` | **Mantener** | Aísla el código generado dentro del directorio del proyecto. |
| Interrupción en caliente | `freephdlabor/interaction/` | **Mantener** | Mecanismo natural para las puertas humanas obligatorias (§9). |
| Log de llamadas LLM | `freephdlabor/logging/llm_logger.py` | **Mantener** | `agent_llm_calls.jsonl` sirve como pista de auditoría del proceso. |
| Edición de ficheros | `…/general_tools/file_editing/` | **Mantener** | Genérico, sin dependencia de dominio. |
| Selector de modelo | `freephdlabor/utils.py::create_model()` | **Reescribir** | Hoy exige `os.environ["ANTHROPIC_API_KEY"]` con acceso directo (KeyError si falta). Debe pasar a router multiproveedor por rol (§3). |
| Búsqueda bibliográfica | `freephdlabor/toolkits/paper_search_tool.py` | **Reescribir** | Semantic Scholar con `S2_API_KEY`, clave que ni figura en `.env`. Además está **desactivada**: comentada en `ideation_agent.py:67`. Sustituir por PubMed + Europe PMC + OpenAlex + Crossref. |
| Descarga arXiv | `…/general_tools/fetch_arxiv_papers/` | **Eliminar** | arXiv es irrelevante en cirugía. Sustituir por Europe PMC full-text OA + Unpaywall. |
| Motor de experimentos | `freephdlabor/toolkits/run_experiment_tool.py`, `external_tools/run_experiment_tool/` | **Eliminar** | AI-Scientist-v2 completo. Es el grueso del peso del repo y no tiene análogo clínico. |
| ExperimentationAgent | `freephdlabor/agents/experimentation_agent.py` | **Reescribir** | Pasa a `AnalysisAgent`: metaanálisis en R y modelos estadísticos, no entrenamiento. |
| ReviewerAgent | `freephdlabor/agents/reviewer_agent.py` | **Reescribir** | Revisión estilo NeurIPS → verificación ítem a ítem de PRISMA/STROBE/CONSORT. |
| Plantillas LaTeX | `…/toolkits/writeup/icml2024*.sty/.bst` | **Eliminar** | Sustituir por `elsarticle` (Elsevier), `sn-jnl` (Springer/BMC) y estilo Vancouver/AMA. |
| Compilador LaTeX | `…/writeup/latex_compiler_tool.py` | **Reescribir** | Funciona, pero lleva rutas absolutas del autor original codificadas (`/home/tl784/…`, `/gpfs/radev/…`). Limpiar y detectar `tectonic`/`latexmk`. |
| Cliente LLM heredado | `freephdlabor/llm.py` | **Eliminar** | Código muerto y duplicado (dos definiciones de `extract_json_between_markers`, bucles de `print` de depuración). Todo pasa por LiteLLM. |
| Entorno conda | `environment.yml` | **Reescribir** | Arrastra `torch 2.5.1`, `torchvision`, `nvidia-cuda-*`, `wandb`, `tensorboard`. Sin AI-Scientist-v2 sobran: instalación de minutos en vez de decenas de GB. |
| Telemetría Phoenix | `launch_multiagent.py` (import) | **Reescribir** | Se registra en el import de primer nivel: si Phoenix no arranca, no arranca nada. Hacerlo opcional tras un flag. |

**Nota sobre madurez.** `launch_multiagent.py` redirige `stdout` y `stderr` a ficheros nada más
entrar en `main()`; depurar en local es incómodo hasta cambiarlo. Es código de investigación
publicado junto a un paper, no una librería mantenida. Fórkalo por la arquitectura, no esperando
estabilidad.

---

## 3. Modelos y coste real

### 3.1 Aritmética del cribado

Una búsqueda de amplitud normal en cirugía devuelve 1 500–5 000 registros. Con 3 000 registros y
~350 tokens por título + abstract + instrucciones:

| Etapa | Volumen | Tokens entrada | Modelo adecuado |
|---|---:|---:|---|
| Cribado título/abstract (doble pase) | 3 000 × 2 | ~2,1 M | Gratuito/barato; lotes de 20 por llamada → ~300 llamadas |
| Elegibilidad a texto completo | ~120 PDF | ~1,2 M | Modelo medio |
| Extracción de datos (40 variables) | ~60 estudios | ~0,9 M | Modelo fuerte: un error aquí contamina el metaanálisis |
| Riesgo de sesgo (RoB 2 / ROBINS-I) | ~60 estudios | ~0,7 M | Modelo fuerte, con cita textual obligatoria |
| Redacción + revisión + cumplimiento | ~15 iteraciones | ~0,5 M | Modelo fuerte |

Total: **4–6 M de tokens de entrada por revisión**, de los cuales el ~55 % es cribado mecánico.
Esa asimetría dicta el enrutado.

### 3.2 Enrutado por rol, no por agente

`create_model()` devuelve hoy un único modelo para todo el sistema. Sustituir por un router
declarado en `.llm_config.yaml`, con una entrada por rol:

| Rol | Con Claude Pro | Con "API gratis" | Nota |
|---|---|---|---|
| `screening` | No usarlo aquí — agota la cuota | Gemini Flash (AI Studio) o Groq | Lotes de 20 registros; ~150–300 llamadas encajan en cuotas diarias gratuitas |
| `extraction` | Claude Code sobre lotes pequeños | Gemini Pro free tier | Salida JSON con esquema fijo y cita textual de origen |
| `judgment` (RoB, GRADE, discusión) | Claude Pro, interactivo | Sin equivalente gratuito fiable | Donde la calidad se nota y donde el humano revisa |
| `deterministic` | Ningún LLM: Python + R | ídem | Deduplicación, recuentos PRISMA, metaanálisis, gráficos |

### 3.3 Confidencialidad — el filtro que descarta las capas gratuitas

Las capas gratuitas de la mayoría de proveedores **usan tus datos para entrenar**. Con literatura
publicada es irrelevante. Con datos de pacientes —aunque seudonimizados— es inaceptable y, en la
UE, un problema de RGPD. Regla dura: **ninguna herramienta que toque una fila de datos clínicos
puede enrutarse a un proveedor de capa gratuita**. Los conjuntos con acuerdo de uso
(PhysioNet/MIMIC, SEER) llevan cláusulas explícitas sobre transferencia a terceros; revisa el DUA
antes, no después.

Implementación: marcar cada herramienta con `data_sensitivity: public | restricted` y que el
router **rechace por diseño** la combinación `restricted` + free-tier, en vez de confiar en que
el agente se acuerde.

### 3.4 Regla de oro de coste

Todo lo determinista sale del LLM. Deduplicar por DOI/PMID normalizado + coincidencia difusa de
títulos (`rapidfuzz`) es exacto, gratis y reproducible; pedírselo a un modelo es caro, no
reproducible y falla. Igual para los recuentos del diagrama PRISMA: salen de consultas SQL, no de
la memoria del agente.

---

## 4. Tres vías de ejecución

La arquitectura de dominio (§5) es idéntica en las tres. Cambia dónde vive el orquestador.

| Vía | Qué es | A favor | En contra |
|---|---|---|---|
| **A · Nativa en Claude Code** *(recomendada)* | Pipeline como skills + subagentes de Claude Code, scripts Python/R deterministas y servidores MCP para bases documentales | Usa la suscripción Pro por su vía prevista; cero infraestructura; las puertas humanas son la conversación misma; produces en días | Sin bucle autónomo 24/7; techo por cuota; menos portable |
| **B · Fork completo** | Python + smolagents, router multiproveedor, ejecución desatendida en VPS barato | Autonomía real; reproducible desde CLI; independiente del proveedor | 4–8 semanas antes del primer resultado; las capas gratuitas limitan por peticiones/día, así que "24/7" es en realidad "lotes nocturnos" |
| **C · Híbrida** | Worker Python autónomo solo para cribado y extracción masiva con modelos gratuitos; el resto en Claude Code | El volumen donde es barato, el juicio donde es bueno; worker pequeño y testeable | Dos entornos que mantener y un contrato de datos entre ambos |

**Recomendación:** empezar por **A**, migrar a **C** cuando el cribado manual duela. **B** solo se
justifica si vas a encadenar muchas revisiones al año o quieres publicar la herramienta.

En A y C conviene evaluar antes de escribir cliente propio los conectores MCP ya disponibles
(Elicit — con búsqueda de artículos, de ensayos y revisión sistemática —, Consensus, Scholar
Gateway).

---

## 5. Arquitectura objetivo

### 5.1 Pipeline (revisión sistemática)

```
1 Pregunta → 2 Protocolo [PUERTA] → 3 Búsqueda → 4 Dedup → 5 Cribado
→ 6 Elegibilidad [PUERTA] → 7 Extracción → 8 Sesgo → 9 Análisis
→ 10 Redacción → 11 Integridad → 12 Firma [PUERTA]
```

### 5.2 Plantel de agentes

| Agente | Origen | Responsabilidad | Herramientas clave |
|---|---|---|---|
| `ManagerAgent` | Heredado | Orquesta y aplica las puertas humanas | Delegación, workspace |
| `ClinicalQuestionAgent` | Sustituye `IdeationAgent` | PICO/PICOTS, criterios FINER, comprobación de que la revisión no existe ya | PubMed, PROSPERO, ClinicalTrials.gov |
| `LiteratureAgent` | Nuevo | Ejecuta y versiona la estrategia de búsqueda; recupera texto completo OA | E-utilities, Europe PMC, Crossref, OpenAlex, Unpaywall |
| `ScreeningAgent` | Nuevo | Doble pase independiente, κ de Cohen, lista de conflictos | Lotes contra SQLite del proyecto |
| `ExtractionAgent` | Nuevo | Extrae a esquema bloqueado; cada celda con cita textual y página | Lector de PDF, validador de esquema |
| `BiasAgent` | Nuevo | RoB 2, ROBINS-I, QUADAS-2 o NOS dominio a dominio con justificación | Plantillas de dominio, `robvis` |
| `AnalysisAgent` | Reescribe `ExperimentationAgent` | Metaanálisis, heterogeneidad, subgrupos, sesgo de publicación, sensibilidad | R (`meta`, `metafor`, `dmetar`) vía subproceso |
| `WriteupAgent` | Heredado, replantillado | Manuscrito IMRaD en LaTeX, tablas, figuras, bibliografía Vancouver | `elsarticle`/`sn-jnl`, compilador LaTeX |
| `ComplianceAgent` | Reescribe `ReviewerAgent` | Verifica ítem a ítem la guía que toque; genera el checklist como suplementario | PRISMA 2020, STROBE, CONSORT 2025, TRIPOD+AI |
| `IntegrityAgent` | Nuevo | Ninguna cita ni cifra sin origen verificable (§7) | Resolución DOI/PMID, libro mayor de procedencia |

### 5.3 El workspace es el contrato

```
results/2026-09-02_lap-vs-open-appy/
├── protocol.md            # PICO, criterios, plan de análisis — congelado tras la puerta G1
├── review.sqlite          # fuente única: registros, decisiones, extracciones, sesgo
├── search/
│   ├── strategy.yaml      # consulta exacta por base y fecha de ejecución
│   └── raw_pubmed.json    # respuesta sin tocar — reproducibilidad
├── screening/
│   ├── pass_a.jsonl · pass_b.jsonl
│   └── conflicts.csv      # lo que revisa el humano
├── extraction/
│   ├── schema.json        # esquema bloqueado antes de extraer
│   └── studies.csv        # una fila por estudio, cada celda con cita de origen
├── analysis/
│   ├── meta.R · results.json
│   └── figures/forest_primary.pdf · funnel.pdf
├── manuscript/
│   ├── main.tex · references.bib
│   └── prisma_checklist.md
└── provenance.jsonl       # cada cifra del manuscrito → su origen
```

---

## 6. Qué significa "experimentar" aquí

| Vía | Descripción | Fricción de entrada |
|---|---|---|
| **A · Revisión sistemática y metaanálisis** | Publicable, valorada en cirugía, insumo 100 % público. Vía por defecto del sistema. | Baja. Requisito de calidad: registro previo en PROSPERO y protocolo congelado antes de cribar. |
| **B · Análisis secundario de datos abiertos** | NHANES, SEER, MIMIC-IV, eICU. Cohortes retrospectivas (STROBE) o modelos predictivos (TRIPOD+AI). | Media. PhysioNet exige formación CITI + credencial + DUA restrictivo. |
| **C · Modelización y bibliometría** | Markov y coste-efectividad (CHEERS), bibliometría de un campo quirúrgico, revisiones de alcance (PRISMA-ScR). | Mínima; techo de impacto también menor. |

### Fuentes de datos y su fricción real

| Fuente | Acceso | API | Advertencia |
|---|---|---|---|
| PubMed / MEDLINE | Abierto | E-utilities, sin clave (clave gratuita sube el límite) | Base mínima obligatoria; solo PubMed no basta para una SR seria |
| Europe PMC | Abierto | REST, sin clave | Texto completo OA: clave para la extracción |
| OpenAlex | Abierto | REST, sin clave | Sustituto sólido de Semantic Scholar |
| Crossref | Abierto | REST, sin clave | Verificación canónica de DOI para la capa de integridad |
| ClinicalTrials.gov | Abierto | API v2 | Detecta sesgo de publicación: ensayos registrados nunca publicados |
| Embase | Suscripción | Elsevier, de pago | **Punto débil real:** los revisores penalizan una SR quirúrgica sin Embase |
| Cochrane CENTRAL | Suscripción | Sin API abierta | Exportación manual desde la web |
| PROSPERO | Abierto | Sin API pública | Comprobación de duplicidad manual; no lo automatices a ciegas |
| Google Scholar | Abierto | Sin API; bloquea scraping | Solo búsqueda manual de literatura gris |
| MIMIC-IV / eICU | Credencial PhysioNet | Descarga | El DUA restringe la transferencia a terceros: nunca a APIs de capa gratuita |

---

## 7. Capa de integridad (innegociable)

El fallo característico de los redactores automáticos de papers es inventar citas y cifras. En
medicina eso no es un bug: es mala conducta científica con tu nombre en la portada.

1. **Ninguna cita sin resolver.** Toda entrada de `references.bib` se genera *únicamente* desde
   una respuesta real de PubMed o Crossref, nunca desde la salida de un modelo. Si una referencia
   no resuelve, la compilación **falla** — no avisa. Un aviso que se puede ignorar acaba ignorado.
2. **Ninguna cifra sin procedencia.** Un pase final extrae todos los valores numéricos del
   manuscrito y exige correspondencia con una clave de `provenance.jsonl` que apunte a una fila de
   `studies.csv` o a una salida de `results.json`. Un OR de 0,74 que no rastree hasta el script de
   R detiene el proceso.
3. **Cita textual en cada extracción.** Cada celda guarda la frase literal del artículo con
   página. Hace auditable el trabajo del modelo en 30 s por estudio y es tu defensa si alguien
   cuestiona un dato.
4. **Nunca datos sintéticos en el manuscrito.** Prohibido generar "datos de ejemplo" en cualquier
   fichero que alimente el manuscrito. Los fixtures viven en `tests/` y el pipeline se niega a
   leer de ahí.
5. **Divulgación del uso de IA.** El sistema inserta en Métodos qué modelos se usaron, en qué
   etapas y quién verificó. El ICMJE no admite a la IA como autora y exige declararla.

---

## 8. Cumplimiento normativo

El `ComplianceAgent` selecciona la guía por diseño de estudio, verifica ítem a ítem y produce el
checklist rellenado como material suplementario — exactamente lo que pedirá la revista.

| Diseño | Guía | Salida generada |
|---|---|---|
| Revisión sistemática / metaanálisis | PRISMA 2020 | Checklist 27 ítems + diagrama de flujo con recuentos reales |
| Revisión de alcance | PRISMA-ScR | Checklist 20 ítems |
| Observacional (cohorte, casos-controles) | STROBE | Checklist 22 ítems |
| Ensayo clínico aleatorizado | CONSORT 2025 | Checklist + diagrama de flujo |
| Protocolo de ensayo | SPIRIT | Checklist de protocolo |
| Precisión diagnóstica | STARD | Checklist + diagrama |
| Modelo predictivo (con o sin IA) | TRIPOD+AI | Checklist + calibración y discriminación |
| Caso clínico | CARE | Checklist + línea temporal |
| Mejora de calidad asistencial | SQUIRE 2.0 | Checklist 18 ítems |
| Evaluación económica | CHEERS 2022 | Checklist 28 ítems |
| Innovación quirúrgica | Marco IDEAL (0–4) | Clasificación de etapa y requisitos de reporte |

**IDEAL merece atención especial en cirugía:** define en qué etapa está una técnica (idea,
desarrollo, exploración, evaluación, seguimiento a largo plazo) y qué se puede afirmar en cada
una. Un agente que no lo conoce redacta conclusiones de etapa 3 con datos de etapa 2a — la forma
más rápida de que un revisor quirúrgico rechace el manuscrito.

---

## 9. Puertas humanas obligatorias

| Puerta | Momento | Qué revisas | Coste de saltártela |
|---|---|---|---|
| **G1 · Protocolo** | Antes de buscar | PICO, criterios, estrategia de búsqueda, plan de análisis | Criterios ajustados a posteriori: la revisión pierde validez entera |
| **G2 · Conflictos de cribado** | Tras el doble pase | Desacuerdos + muestra aleatoria del 10 % de los acuerdos | Exclusiones sistemáticamente sesgadas que nadie detecta |
| **G3 · Extracción** | Antes del análisis | 20 % de las filas contra el PDF original, priorizando desenlaces primarios | Un metaanálisis preciso sobre datos incorrectos |
| **G4 · Interpretación** | Antes de la discusión | Que las conclusiones no excedan lo que soportan el I² y la certeza GRADE | Sobreinterpretación: el motivo de rechazo más frecuente |
| **G5 · Firma** | Antes de enviar | Manuscrito, checklist, declaración de IA, autoría ICMJE | Tu responsabilidad profesional, sin matices |

**Implementación:** la puerta escribe `gate_G3.approved` con marca de tiempo y hash del artefacto
revisado. Sin ese fichero, la etapa siguiente aborta. El canal de interrupción de `freephdlabor`
(`freephdlabor/interaction/`) ya da el mecanismo de entrada; hay que invertir la lógica: en vez de
que el humano interrumpa cuando quiere, el agente se bloquea hasta que el humano contesta.

---

## 10. Plan por fases

Estimaciones para una persona con dedicación parcial. Cada fase produce algo utilizable por sí
solo y ninguna depende de que exista la siguiente.

### F0 · Decidir la vía y montar el esqueleto — 2–3 días
- Elegir vía A, B o C (§4). Si es A, el "repo" es un proyecto de Claude Code con `CLAUDE.md`,
  skills y scripts.
- Fijar el esquema de `review.sqlite` y la estructura del workspace: es el contrato del que cuelga
  todo lo demás.
- Probar a mano las cuatro APIs base (PubMed, Europe PMC, Crossref, ClinicalTrials.gov) y los
  conectores MCP disponibles sobre una pregunta clínica real tuya.
- **Entregable:** una pregunta PICO propia y 200 registros descargados y deduplicados. Si esto no
  funciona, nada más importa.

### F1 · Núcleo determinista — 1 semana (Python + R puros, cero LLM)
- Cliente de búsqueda multibase con versionado de la estrategia y volcado crudo de respuestas.
- Deduplicación por DOI/PMID normalizado + `rapidfuzz` sobre títulos.
- Generador del diagrama PRISMA a partir de consultas SQL, no de texto.
- Script de metaanálisis en R (`meta`/`metafor`) que consume `studies.csv` y emite `results.json`
  + forest y funnel plots.
- **Entregable:** con un CSV extraído a mano ya obtienes un metaanálisis reproducible. Solo esto
  ahorra días.

### F2 · Cribado y extracción asistidos — 2 semanas
- `ScreeningAgent`: lotes de 20 registros, doble pase independiente, κ de Cohen, `conflicts.csv`.
- **Calibración obligatoria:** antes de confiar en él, cribas 100 registros a mano y comparas. Si
  la sensibilidad no llega a ~0,95, el cribado automático no vale: en una SR un falso negativo es
  un estudio perdido para siempre.
- `ExtractionAgent` con esquema bloqueado y cita textual por celda.
- Router multiproveedor por rol y marcado `data_sensitivity`.
- **Entregable:** cribado de 3 000 registros en horas, con fiabilidad medida, no supuesta.

### F3 · Sesgo, redacción y cumplimiento — 2–3 semanas
- `BiasAgent` con plantillas RoB 2 / ROBINS-I / QUADAS-2 y justificación citada por dominio.
- Replantillado LaTeX: fuera ICML, dentro `elsarticle` y `sn-jnl` con bibliografía Vancouver;
  limpieza de las rutas absolutas del compilador.
- `ComplianceAgent` con PRISMA 2020 como primera guía; el resto se añaden como ficheros de datos,
  no como código.
- `IntegrityAgent` con las cinco reglas de §7 y fallo duro.
- **Entregable:** primer borrador completo con checklist PRISMA relleno y cero citas inventadas.

### F4 · Validación contra una revisión ya publicada — 1 semana
- Coge una SR publicada en tu área, reproduce su búsqueda con el sistema y compara: ¿recupera los
  mismos estudios incluidos? ¿los mismos tamaños de efecto?
- Documenta la discrepancia. Ese informe es lo que te permite defender el método ante un revisor y
  lo que te dice dónde miente el sistema.
- **Entregable:** informe de validación. Sin él no tienes una herramienta de investigación, tienes
  un generador de texto plausible.

---

## 11. Riesgos, ordenados por daño

| Riesgo | Probabilidad | Mitigación estructural |
|---|---|---|
| Citas o cifras fabricadas llegan al manuscrito | Alta sin control | §7: resolución obligatoria contra API y libro mayor de procedencia, con fallo duro de compilación |
| El cribado descarta estudios relevantes | Media | Calibración medida contra 100 registros manuales; doble pase; revisión del 10 % de acuerdos |
| Datos de pacientes enviados a proveedor de capa gratuita | Media | Marcado `data_sensitivity` aplicado en el router, no confiado al criterio del agente |
| Cuota de Claude Pro agotada a mitad de proceso | Alta en vía B | Enrutado por rol; volumen a modelos gratuitos; ejecución por lotes con reanudación desde el workspace |
| Búsqueda incompleta (sin Embase/CENTRAL) | Alta | Declararlo como limitación explícita y complementar con exportación manual institucional |
| Sobreinterpretación de resultados heterogéneos | Media | Puerta G4 + certeza GRADE obligatoria antes de redactar conclusiones |
| Revista rechaza por uso no declarado de IA | Baja | Declaración autogenerada en Métodos; revisión de la política concreta de la revista en G5 |
| El fork queda desalineado del upstream | Alta | Asumido: al eliminar AI-Scientist-v2 el fork diverge irreversiblemente. Tratarlo como base, no como dependencia. |

---

## 12. Lo que este sistema no hará

- **No diseña ni ejecuta estudios prospectivos.** Sin recogida primaria, reclutamiento ni
  aleatorización: eso requiere comité de ética y responsables humanos identificados.
- **No sustituye el registro en PROSPERO** ni la aprobación del CEIm cuando corresponda.
- **No firma.** El ICMJE no admite a la IA como autora; los criterios de autoría los cumples tú y
  la responsabilidad sobre cada cifra es tuya.
- **No toca datos identificables de pacientes** con proveedores de capa gratuita, ni con ninguno
  sin el acuerdo de tratamiento correspondiente.
- **No garantiza publicación.** Reduce el tiempo de las tareas mecánicas y hace el proceso
  auditable; la calidad de la pregunta clínica sigue siendo el factor determinante y no se
  automatiza.
