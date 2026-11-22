"""Gestión de memoria virtual paginada para Blissey OS (Prototipo 2: RM1, RM3)."""

from __future__ import annotations

from typing import Optional

from .errores import lanzar_error_memoria, lanzar_error_sin_marcos

_marcos_totales: int = 16
_tam_pagina: int = 256
_marcos_libres: list[int] = []
_dueno_marco: dict[int, tuple[int, int]] = {}  # marco -> (pid, pagina)
_tablas_paginas: dict[int, dict[int, dict]] = {}  # pid -> {pagina: entrada}
_orden_lru: list[tuple[int, int]] = []  # [(pid, pagina), ...] del menos reciente al más reciente

_accesos: int = 0
_fallos: int = 0
_reemplazos: int = 0
_escrituras_a_swap: int = 0
_historial_fallos: list[bool] = []


def _reiniciar_modulo(marcos_fisicos: int = 16, tam_pagina: int = 256) -> None:
    """Reinicia las estructuras de paginación, marcos físicos y métricas de memoria."""
    global _marcos_totales, _tam_pagina, _marcos_libres, _dueno_marco
    global _tablas_paginas, _orden_lru, _accesos, _fallos, _reemplazos
    global _escrituras_a_swap, _historial_fallos

    _marcos_totales = max(1, int(marcos_fisicos))
    _tam_pagina = max(1, int(tam_pagina))
    _marcos_libres = list(range(_marcos_totales))
    _dueno_marco = {}
    _tablas_paginas = {}
    _orden_lru = []

    _accesos = 0
    _fallos = 0
    _reemplazos = 0
    _escrituras_a_swap = 0
    _historial_fallos = []


def _asegurar_tabla_proceso(pid: int) -> tuple[dict[int, dict], dict]:
    """Obtiene el PCB del proceso e inicializa su tabla de páginas si aún no existe."""
    from . import procesos

    pcb = procesos._obtener_pcb(pid)
    if pid not in _tablas_paginas:
        mem_bytes = int(pcb["memoria_bytes"])
        num_paginas = max(1, (mem_bytes + _tam_pagina - 1) // _tam_pagina) if mem_bytes > 0 else 0
        _tablas_paginas[pid] = {
            pag: {
                "marco": None,
                "presente": False,
                "modificada": False,
                "referenciada": False,
            }
            for pag in range(num_paginas)
        }
    return _tablas_paginas[pid], pcb


def _marcar_uso_lru(pid: int, pagina: int) -> None:
    """Actualiza la posición de (pid, pagina) como la más recientemente usada."""
    clave = (pid, pagina)
    if clave in _orden_lru:
        _orden_lru.remove(clave)
    _orden_lru.append(clave)


def _desalojar_victima(candidatos: list[tuple[int, int]]) -> tuple[int, tuple[int, int]]:
    """Selecciona y desaloja la página menos recientemente usada entre los candidatos."""
    global _reemplazos, _escrituras_a_swap

    victima: Optional[tuple[int, int]] = None
    for clave in _orden_lru:
        if clave in candidatos:
            victima = clave
            break

    if victima is None:
        victima = candidatos[0]

    v_pid, v_pag = victima
    entrada_v = _tablas_paginas[v_pid][v_pag]
    marco_liberado = entrada_v["marco"]

    if entrada_v["modificada"]:
        _escrituras_a_swap += 1

    entrada_v["marco"] = None
    entrada_v["presente"] = False
    entrada_v["modificada"] = False
    entrada_v["referenciada"] = False

    if victima in _orden_lru:
        _orden_lru.remove(victima)
    if marco_liberado in _dueno_marco:
        del _dueno_marco[marco_liberado]

    _reemplazos += 1
    return marco_liberado, victima


def acceder_memoria(pid: int, direccion_virtual: int, escritura: bool = False) -> dict:
    """Traduce una dirección virtual a marco físico delegando fallos a errores.py (RM3)."""
    global _accesos, _fallos

    tabla, pcb = _asegurar_tabla_proceso(pid)
    mem_bytes = int(pcb["memoria_bytes"])
    dir_v = int(direccion_virtual)

    if mem_bytes <= 0 or dir_v < 0 or dir_v >= mem_bytes:
        lanzar_error_memoria(pid=pid, direccion=dir_v, limite=mem_bytes)

    _accesos += 1
    pagina = dir_v // _tam_pagina
    entrada = tabla[pagina]

    # Acierto de página residente
    if entrada["presente"] and entrada["marco"] is not None:
        entrada["referenciada"] = True
        if escritura:
            entrada["modificada"] = True
        _marcar_uso_lru(pid, pagina)
        _historial_fallos.append(False)
        return {
            "marco": entrada["marco"],
            "fallo_pagina": False,
            "pagina_reemplazada": None,
        }

    # Fallo de página
    _fallos += 1
    _historial_fallos.append(True)

    cuota = max(1, int(pcb["cuota_marcos"]))
    residentes_pid = [
        (pid, p) for p, info in tabla.items() if info["presente"] and info["marco"] is not None
    ]

    pagina_reemplazada: Optional[tuple[int, int]] = None
    if len(residentes_pid) < cuota and _marcos_libres:
        marco_asignado = _marcos_libres.pop(0)
    elif residentes_pid:
        marco_asignado, pagina_reemplazada = _desalojar_victima(residentes_pid)
    elif _orden_lru:
        marco_asignado, pagina_reemplazada = _desalojar_victima(list(_orden_lru))
    else:
        lanzar_error_sin_marcos(pid=pid)

    entrada["marco"] = marco_asignado
    entrada["presente"] = True
    entrada["referenciada"] = True
    entrada["modificada"] = bool(escritura)

    _dueno_marco[marco_asignado] = (pid, pagina)
    _marcar_uso_lru(pid, pagina)

    return {
        "marco": marco_asignado,
        "fallo_pagina": True,
        "pagina_reemplazada": pagina_reemplazada,
    }


def tabla_paginas(pid: int) -> dict:
    """Devuelve una copia de la tabla de páginas del proceso."""
    tabla, _ = _asegurar_tabla_proceso(pid)
    return {
        pag: {
            "marco": info["marco"],
            "presente": info["presente"],
            "modificada": info["modificada"],
            "referenciada": info["referenciada"],
        }
        for pag, info in tabla.items()
    }


def liberar_memoria(pid: int) -> int:
    """Libera todos los marcos físicos ocupados por el proceso y devuelve la cantidad liberada."""
    if pid not in _tablas_paginas:
        return 0

    tabla = _tablas_paginas.pop(pid)
    liberados = 0
    for pag, info in tabla.items():
        marco = info["marco"]
        if info["presente"] and marco is not None:
            liberados += 1
            if marco in _dueno_marco:
                del _dueno_marco[marco]
            if marco not in _marcos_libres:
                _marcos_libres.append(marco)
        clave = (pid, pag)
        if clave in _orden_lru:
            _orden_lru.remove(clave)

    _marcos_libres.sort()
    return liberados


def estado_memoria() -> dict:
    """Devuelve el estado actual de marcos físicos y fragmentación interna."""
    from . import procesos

    marcos_por_proceso: dict[int, int] = {}
    frag_interna = 0

    for pid, tabla in _tablas_paginas.items():
        residentes = [p for p, info in tabla.items() if info["presente"] and info["marco"] is not None]
        if residentes:
            marcos_por_proceso[pid] = len(residentes)
            pcb = procesos._procesos.get(pid)
            if pcb is not None:
                mem_bytes = int(pcb["memoria_bytes"])
                residuo = mem_bytes % _tam_pagina
                ultima_pag = max(tabla.keys())
                if residuo != 0 and ultima_pag in residentes:
                    frag_interna += _tam_pagina - residuo

    return {
        "marcos_totales": _marcos_totales,
        "marcos_libres": len(_marcos_libres),
        "marcos_por_proceso": marcos_por_proceso,
        "fragmentacion_interna_bytes": frag_interna,
    }


def metricas_memoria() -> dict:
    """Devuelve las métricas acumuladas de accesos, fallos y reemplazos de página."""
    tasa = (_fallos / _accesos) if _accesos > 0 else 0.0
    return {
        "accesos": _accesos,
        "fallos_pagina": _fallos,
        "tasa_fallos": round(tasa, 4),
        "reemplazos": _reemplazos,
        "escrituras_a_swap": _escrituras_a_swap,
    }


def detectar_hiperpaginacion() -> bool:
    """Detecta hiperpaginación (thrashing) cuando la tasa reciente de fallos supera el 50%."""
    ventana = _historial_fallos[-20:]
    if len(ventana) < 8:
        return False
    return (sum(1 for f in ventana if f) / len(ventana)) > 0.50


def politica_reemplazo() -> str:
    """Nombre del algoritmo de reemplazo de páginas."""
    return "LRU"