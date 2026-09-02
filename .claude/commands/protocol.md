Ayuda al usuario a redactar el protocolo de una revisión sistemática/metaanálisis y prepáralo para la puerta G1.

## Argumentos: $ARGUMENTS

Se espera: `workspace=<ruta>` (p. ej. `results/2026-tapp-vs-lichtenstein`) y, si el usuario ya lo dio en el chat, la pregunta clínica en bruto.

## Pasos

1. Si el workspace no existe todavía, créalo:
   ```bash
   python -m jordilabor init <workspace>
   ```

2. Lee `<workspace>/protocol.md`. Si está vacío (plantilla), guía al usuario con preguntas concretas — no rellenes tú los criterios por tu cuenta:
   - **PICO/PICOTS**: población, intervención, comparación, desenlace primario y secundarios, diseños elegibles.
   - **Criterios de inclusión/exclusión**: sé exhaustivo — idioma, año, tipo de publicación (¿se aceptan abstracts de congreso?), tamaño muestral mínimo si aplica.
   - **Estrategia de búsqueda**: propón una cadena de búsqueda PubMed concreta a partir del PICO (usa MeSH cuando tenga sentido) y pídele al usuario que la valide o ajuste. No la des por buena sin que él la revise.
   - **Plan de análisis**: medida de efecto, modelo (aleatorio/fijo), subgrupos y sensibilidad previstos ANTES de ver los datos — si se deciden después, adviértelo explícitamente como desviación del protocolo.

3. Comprueba si ya existe una revisión igual en PROSPERO: busca en PubMed/Europe PMC términos del PICO combinados con "systematic review" o "meta-analysis" y dile al usuario lo que encuentres. Tú no tienes acceso a la API de PROSPERO (no es pública) — dile que lo compruebe manualmente en https://www.crd.york.ac.uk/prospero/ antes de registrar.

4. Escribe el protocolo final en `<workspace>/protocol.md` con `Edit`, preservando la estructura de secciones de la plantilla.

5. Antes de cerrar, léeselo de vuelta al usuario en un resumen corto y pregúntale explícitamente si lo aprueba. Solo entonces:
   ```bash
   python -m jordilabor gate approve G1 <workspace>/protocol.md --workspace <workspace> --by "<nombre que te dé el usuario>"
   ```
   No apruebes G1 sin que el usuario lo haya confirmado en esta conversación.

## Recuerda
No estás redactando el protocolo solo — tu trabajo es proponer una cadena de búsqueda y una estructura razonables y forzar que el usuario tome las decisiones de PICO/criterios explícitamente, porque de esto depende toda la validez de la revisión.
