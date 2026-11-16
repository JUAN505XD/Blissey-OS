# Blissey OS (`minidc`) - Simulador de Sistema Operativo para Urgencias Hospitalarias

Sistema operativo simulado desarrollado en Python 3.11+ (biblioteca estándar) basado en la arquitectura de **Aurora OS**, modelado para la gestión de atención de urgencias hospitalarias mediante reloj de tiempo discreto[cite: 1, 2].

## Arquitectura y Módulos (`minidc/`)

* `kernel.py`: Reloj discreto y ciclo determinista de 7 pasos (*Reloj, Llegadas, E/S terminada, Planificador, Ejecución, Vigilancia, Métricas*)[cite: 1, 4].
* `procesos.py`: Gestión de estados (`NUEVO`, `LISTO`, `EJECUTANDO`, `BLOQUEADO`, `TERMINADO`) y planificador por triage/urgencia con quantum corto y envejecimiento (`RP1`, `RP2`, `RP3`)[cite: 1, 4, 6].
* `consola.py`: Intérprete de comandos administrativos y clínicos (`admitir`, `run`, `ps`, `kill`, `tick`, `top`, `free`, `df`, `pwd`, `whoami`) con directorios independientes por usuario[cite: 1, 5].
* `memoria.py`, `disco.py`, `archivos.py`, `sincronizacion.py`, `errores.py`: Subsistemas desacoplados y jerarquía de excepciones[cite: 1, 3].

## Ejecución de pruebas automatizadas

Desde la raíz del repositorio:

```bash
python -m pytest