# AGENTS.md

Instrucciones para cualquier agente (humano o IA) que explore, analice o extienda `moneybot`.

## 0. Qué es esto y por qué importa el cuidado

`moneybot` está pensado para operar **live** en una cuenta real de Alpaca (ver [readme.md](readme.md)).
No es un sandbox: `services/collector/src/jobs.py:guard_live` aborta si `mode != live` o si
`APCA_API_BASE_URL` apunta a paper. **Hoy no opera**: no hay servicio `trade` y `decide()` vive solo
en `research/` (ver `brain/architecture/0004-servicios.md`). Si vuelve un servicio `trade`, debe
traer de vuelta un flag de armado (`trading_enabled`) apagado por defecto.

Regla de oro: **nunca** cambies `trading_enabled` a `true`, ni el cron de Terraform, ni nada bajo
`infra/` o `.github/workflows/`, sin que el usuario lo pida explícitamente para ese cambio.

## 1. Mapa del repo

- [research/src/strategy.py](research/src/strategy.py) — `decide()` y `Decision`. Pura, sin I/O.
  Patrón Scherman (SMA 200 de tendencia, 3er día bajista, salida por SMA 5).
- [research/src/backtest.py](research/src/backtest.py), [portfolio.py](research/src/portfolio.py) —
  backtest y cartera, solo locales. Tests en `research/tests/`.
- [services/collector/](services/collector) — único servicio desplegado: jobs `snapshot` y `bars`
  (`src/jobs.py`, `src/bars.py`, `src/db.py`). Tests en `services/collector/tests/`.
- [config/bot.yml](config/bot.yml) — `mode`, `symbol`, `feed`. Va dentro de la imagen.
- [dbt/](dbt) — vistas y modelos en BigQuery. Las tablas que escribe el collector las crea Terraform.
- [infra/](infra), [.github/workflows/](.github/workflows) — Cloud Run Jobs, Scheduler, BigQuery,
  CI/CD. Cambios aquí son infraestructura, no exploración.

## 2. Estilo a mantener

El código ya sigue estas convenciones; nuevo código debe encajar, no inventar las suyas:

- Type hints en toda firma pública. `Decision` es un `@dataclass(frozen=True)`.
- `strategy.py` se mantiene puro (sin red, sin DB, sin reloj). Si una función necesita I/O, va en
  un servicio (`jobs.py` o `db.py`), no mezclada con la decisión.
- Sin docstrings salvo cuando el comportamiento no es obvio desde la firma (ver el docstring de
  `decide`). Sin comentarios que expliquen el qué; sólo el por qué cuando no es obvio.
- Atajos conocidos se marcan así, con su límite y su upgrade path:
  ```python
  # ponytail: <qué se está simplificando>
  # Upgrade path: <qué habría que hacer para quitarlo>
  ```
  Si introducís un atajo nuevo, marcalo igual. Si vas a "resolver" uno de estos comentarios,
  hacelo de verdad (no borres el comentario sin cerrar el upgrade).
- Errores: `SystemExit` para fallos de configuración/arranque, excepción normal + `finish_run(...,
  "error", ...)` para fallos de un run. No se traga errores en silencio.
- Nombres de pruebas describen el escenario (`test_falling_trend_does_not_buy`), no el método.

## 3. Cómo explorar alternativas sin arriesgar nada

El 90% de "¿y si cambiamos la estrategia?" se responde sin tocar ningún servicio, sin credenciales y sin
BigQuery: `decide()` es pura.

1. Para explorar una variante de la estrategia: llamá `decide(closes, last, in_position, ...)`
   directamente con listas de precios (reales, descargados, o sintéticos). No necesitás
   `ALPACA_KEY` ni DB para esto.
2. Para probar un job del collector sin red: mockeá los clientes en un test nuevo bajo
   `services/collector/tests/`, como hace `test_collector_db.py` con el cliente de BigQuery.
3. Nunca apuntes `APCA_API_BASE_URL` a paper esperando que "funcione en modo seguro": el guard lo
   rechaza.
4. Todo experimento (nueva variante de `decide`, nuevo indicador, cambio de ventana, etc.) se
   analiza primero en `brain/proposals/` (ver sección 5) antes de tocar código en una rama.

## 4. Ramas: una por funcionalidad o experimento

Cada funcionalidad nueva o experimento vive en su propia rama, nunca mezclado en `main` ni en
`dev` a medio terminar.

- Nomenclatura: `feat/<slug>` para funcionalidad decidida, `exp/<slug>` para una alternativa que
  todavía se está evaluando (puede no llegar a mergearse).
- Antes de abrir la rama, crear la entrada correspondiente en `brain/proposals/` (ver abajo).
- Los tests de la sección 7 deben pasar antes de pedir review o mergear.
- Si el experimento se descarta, la rama no se mergea, pero la entrada en `brain/proposals/` queda
  con el resultado y el motivo — ese es el valor, no el código.

## 5. La carpeta `brain/`

`brain/` es la base de conocimiento local del proyecto: qué se analizó, qué se decidió, por qué, y
un resumen de cómo funciona el bot hoy para alguien que llega nuevo. **Se versiona**
(`!brain/` en `.gitignore`). Si la conclusión de algo
en `brain/` debe sobrevivir y compartirse con el equipo, promovela a `README.md`, a un comentario
`ponytail:` en el código, o a la descripción del PR; `brain/` por sí sola no es la fuente de verdad
compartida.

Si `brain/` no existe en tu checkout, recreala con esta estructura antes de usarla:

```
brain/
  README.md              # este contrato, resumido
  overview.md            # "cómo funciona el bot hoy", mental model actualizado
  architecture/
    0000-baseline.md     # snapshot de arquitectura actual (punto de partida)
    NNNN-<slug>.md        # una entrada por decisión de arquitectura posterior
  proposals/
    TEMPLATE.md
    <fecha>-<slug>.md     # una por propuesta/alternativa analizada
```

Reglas de uso:

- **Antes** de empezar a explorar una alternativa, copiá `brain/proposals/TEMPLATE.md` a
  `brain/proposals/<fecha>-<slug>.md` y completá el problema y las alternativas consideradas.
- **Al decidir**, completá la decisión, el motivo y la rama/PR en esa misma entrada. No se borran
  propuestas descartadas — quedan como registro de qué ya se probó y por qué no.
- Si la decisión cambia la arquitectura (no sólo un parámetro), añadí una entrada nueva en
  `brain/architecture/` que referencie la propuesta.
- Si la decisión cambia cómo funciona el bot para quien lo lee por primera vez, actualizá
  `brain/overview.md` en la misma rama.

## 6. Variables de entorno

- `ALPACA_KEY` / `ALPACA_SECRET` — cuenta **live** de Alpaca. No hay variante paper utilizable.
- `GCP_PROJECT` / `BQ_DATASET` / `BQ_LOCATION` (por defecto `US`) — BigQuery del collector.
- `BOT_CONFIG` — ruta alternativa a `config/bot.yml`.

## 7. Validar antes de terminar

```bash
PYTHONPATH=services/collector python -m unittest discover -s services/collector/tests
PYTHONPATH=research python -m unittest discover -s research/tests
```

Python 3.12, como en el CI. Si tu cambio toca `strategy.py` o un job, agregá un caso de test en
lugar de validar a mano.
