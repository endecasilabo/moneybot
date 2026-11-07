# brain/

Base de conocimiento del proyecto. Se versiona (`!brain/` en `.gitignore`). El contrato completo de uso está en
[AGENTS.md](../AGENTS.md#5-la-carpeta-brain), esto es el resumen.

- `overview.md` — cómo funciona el bot hoy, mental model para alguien que llega nuevo.
- `architecture/` — una entrada por decisión de arquitectura, empezando por `0000-baseline.md`.
- `proposals/` — una entrada por alternativa analizada (se use o se descarte). Partí de
  `proposals/TEMPLATE.md`.
- `reference/` — referencia de APIs externas tal como las usa el bot (p. ej. `alpaca-api.md`).
- `spikes/` — exploraciones con resultados (gráficos en `spikes/img/`) que no cambian el bot
  live, pero dejan constancia de qué se probó y qué salió.

Si una conclusión de acá debe sobrevivir y compartirse con el equipo, promovela a `README.md` (raíz
del repo), a un comentario `ponytail:` en el código, o a la descripción del PR.
