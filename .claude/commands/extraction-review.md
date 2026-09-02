Verifica una muestra de la extracción de datos contra el PDF original y prepara la puerta G3.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>`.

## Pasos

1. Exporta el CSV actual de estudios:
   ```bash
   python -m freemdlabor extract export --workspace <workspace>
   ```

2. Cuenta cuántas celdas hay en total (nº de estudios incluidos × nº de campos del esquema) y calcula el 20% — ese es el número mínimo de celdas a verificar. Prioriza los desenlaces primarios sobre las variables descriptivas.

3. Para cada celda de la muestra: abre el PDF/texto completo del estudio correspondiente, localiza la cita textual (`quote`) que dejó `ExtractionAgent` en `review.sqlite`, y comprueba tú mismo (o pide al usuario que confirme si el juicio clínico es ambiguo) que:
   - el valor extraído coincide con lo que dice el texto,
   - la cita es real y está donde dice que está (no inventada),
   - la página es razonable.

   Si algo no cuadra, NO lo corrijas en silencio: dile al usuario qué campo falló y por qué, y vuelve a extraer ese estudio si hace falta.

4. Marca cada celda verificada:
   ```bash
   python -m freemdlabor extract verify --workspace <workspace> --record-id <id> --field <campo> --by "<nombre>"
   ```

5. Si encuentras más de 1-2 errores en la muestra del 20%, dilo explícitamente: probablemente haga falta re-extraer con un modelo distinto o revisar el prompt, no seguir adelante con el resto sin verificar.

6. Cuando la muestra esté verificada y el usuario esté conforme:
   ```bash
   python -m freemdlabor gate approve G3 <workspace>/extraction/studies.csv --workspace <workspace> --by "<nombre>"
   ```
