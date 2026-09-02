Revisa los conflictos de cribado título/resumen y prepara la puerta G2.

## Argumentos: $ARGUMENTS

Se espera `workspace=<ruta>`.

## Pasos

1. Confirma que existe G1 aprobado:
   ```bash
   python -m jordilabor gate status --workspace <workspace>
   ```
   Si G1 no está aprobado, para aquí y dilo — no revises cribado sobre un protocolo no congelado.

2. Comprueba la fiabilidad entre pases:
   ```bash
   python -m jordilabor screen kappa --workspace <workspace>
   ```
   Si kappa < 0.6 (o lo que diga `config.yaml`), dilo claramente al usuario: el cribado automático no es fiable todavía y conviene calibrar contra un lote cribado a mano antes de confiar en el resto (ver PLAN.md F2). No sigas como si nada.

3. Exporta y lee los conflictos:
   ```bash
   python -m jordilabor screen conflicts --workspace <workspace>
   ```
   Abre `<workspace>/screening/conflicts_title_abstract.csv`.

4. Para cada conflicto, léele al usuario el título, el resumen (resumido si es largo) y las dos decisiones con sus razones. NO decidas tú — pregunta. Cuando el usuario decida:
   ```bash
   python -m jordilabor screen resolve --workspace <workspace> --record-id <id> --decision include|exclude --by "<nombre>" --reason "<motivo>"
   ```

5. Además de los conflictos, propón revisar una muestra aleatoria del 10% de los registros donde ambos pases coincidieron, como control de calidad (así lo pide G2). Si el usuario detecta un patrón de error sistemático ahí, dilo explícitamente — puede invalidar el cribado en bloque, no es un detalle menor.

6. Cuando todos los conflictos estén resueltos y el usuario esté conforme, aprueba G2:
   ```bash
   python -m jordilabor gate approve G2 <workspace>/screening/conflicts_title_abstract.csv --workspace <workspace> --by "<nombre>"
   ```
