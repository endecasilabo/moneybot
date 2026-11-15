# <fecha> — <título corto de la propuesta>

Estado: en análisis | aceptada | descartada
Rama: `exp/<slug>` o `feat/<slug>`
PR: <link, si existe>

## Problema

Qué no funciona, qué se quiere mejorar, o qué pregunta se está respondiendo.

## Alternativas consideradas

1. **<alternativa A>** — cómo funciona, qué cambiaría en `strategy.py`/`main.py`/infra.
2. **<alternativa B>** — idem.

## Evidencia

Cómo se evaluó (ej.: `decide()` corrida contra N años de cierres, comparación de reasons/acciones,
lectura de la fuente original). Resultados concretos, no impresiones.

## Decisión

Qué se eligió y por qué. Si se descartó todo, decirlo — la entrada queda igual.

## Seguimiento

- Si se aceptó: entrada nueva en `brain/architecture/` si cambia la arquitectura, y actualizar
  `brain/overview.md` si cambia el mental model.
- Si se descartó: nada más que esta entrada como registro de qué ya se probó.
