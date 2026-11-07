# 0002 — Reestructura de `dev` (src/, app/, dbt)

Fecha: 2026-11-07 (traída a `exp/portfolio-rebalancing` por fast-forward desde `origin/dev`,
commits `00881e8..aefb4e8`). No viene de una propuesta de `brain/`: la hizo `dev` directamente.

## Qué cambió

| Antes | Ahora |
|---|---|
| `moneybot/` (paquete) | `src/` (`strategy.py`, `db.py`, `jobs.py`, `backtest.py`, `portfolio.py`) |
| `moneybot/main.py` + `main()` + `python -m moneybot trade` | `src/jobs.py` (sin `main()`) + `app/entrypoint.py trade\|snapshot` |
| `Dockerfile`, `requirements.txt` en la raíz | `app/Dockerfile`, `app/requirements.txt` |
| `schema.sql` aplicado al arrancar | modelos `dbt/` (`runs`, `signals`, `orders`, `*_snapshots`) |
| `config/bot.yaml` | `config/bot.yml` (`BOT_CONFIG` sigue sirviendo de override) |
| `Makefile` (`make test`) | sin Makefile: `python -m unittest discover -s tests` |
| `README.md` | `readme.md` |
| `ci.yml`, `ops.yml`, `cloudbuild.yaml` | `.github/workflows/{build,deploy,infra,test}.yml`, `.github/cloudbuild.yml` |
| `.gitignore` por exclusión | `.gitignore` en whitelist: ignora `*` y re-incluye lo que se versiona |

## Cómo encajó el trabajo de esta rama

- `load_local_env()` sigue en `src/jobs.py`, pero **ya no se llama en el arranque**, porque
  `main()` desapareció. Solo lo usa `src/backtest.py`. Si alguien quiere lanzar
  `app/entrypoint.py` en local leyendo `.env`, tiene que añadir la llamada ahí.
- `src/backtest.py` y `src/portfolio.py` se movieron desde `moneybot/` e importan `src.*`.
- `requirements-dev.txt` apunta ahora a `-r app/requirements.txt` y está re-incluido
  explícitamente en `.gitignore`.
- `.gcloudignore`: `dev` lo borró y esta rama lo había modificado. Queda como archivo local sin
  trackear (el `.gitignore` de `dev` lo re-incluye, así que aparece en `git status`).
- `brain/` **se versiona**: re-incluido con `!brain/` + `!brain/**` en `.gitignore`.

## Pendiente

- `AGENTS.md` (que con la whitelist tampoco se versiona) sigue citando `moneybot/main.py`,
  `config/bot.yaml`, `schema.sql` y `make test`.
