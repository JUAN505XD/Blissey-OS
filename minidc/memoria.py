"""Módulo de gestión de memoria paginada (estructura base para Prototipo 1)."""

from __future__ import annotations

_marcos_totales: int = 16
_tam_pagina: int = 256
_accesos: int = 0
_fallos: int = 0
_reemplazos: int = 0


def _reiniciar_modulo(marcos_fisicos: int = 16, tam_pagina: int = 256) -> None:
    global _marcos_totales, _tam_pagina, _accesos, _fallos, _reemplazos
    _marcos_totales = marcos_fisicos
    _tam_pagina = tam_pagina
    _accesos = 0
    _fallos = 0
    _reemplazos = 0


def acceder_memoria(pid: int, direccion_virtual: int, escritura: bool = False) -> dict:
    global _accesos
    _accesos += 1
    return {"marco": 0, "fallo_pagina": False, "pagina_reemplazada": None}


def tabla_paginas(pid: int) -> dict:
    return {}


def liberar_memoria(pid: int) -> int:
    return 0


def estado_memoria() -> dict:
    return {
        "marcos_totales": _marcos_totales,
        "marcos_libres": _marcos_totales,
        "marcos_por_proceso": {},
        "fragmentacion_interna_bytes": 0,
    }


def metricas_memoria() -> dict:
    tasa = (_fallos / _accesos) if _accesos > 0 else 0.0
    return {
        "accesos": _accesos,
        "fallos_pagina": _fallos,
        "tasa_fallos": round(tasa, 4),
        "reemplazos": _reemplazos,
        "escrituras_a_swap": 0,
    }


def detectar_hiperpaginacion() -> bool:
    return False


def politica_reemplazo() -> str:
    return "LRU"