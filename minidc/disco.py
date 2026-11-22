"""Gestión de disco con planificación LOOK (variante SCAN) y caché de bloques (Prototipo 2: RD1)."""

from __future__ import annotations

from typing import Optional

from .errores import ErrorSistema

_UMBRAL_ENVEJECIMIENTO_DISCO = 140

_bloques_disco: int = 200
_tam_bloque: int = 512
_cache_bloques: int = 8

_posicion_cabezal: int = 0
_direccion_cabezal: int = 1  # 1: ascendente, -1: descendente
_desplazamiento_total: int = 0
_solicitudes_atendidas: int = 0
_cola: list[dict] = []
_solicitud_activa: Optional[dict] = None
_siguiente_id: int = 1
_reloj_ref: int = 0

_cache: list[int] = []  # lista LRU de bloques cacheados
_cache_aciertos: int = 0
_cache_fallos: int = 0


def _reiniciar_modulo(
    bloques_disco: int = 200, tam_bloque: int = 512, cache_bloques: int = 8
) -> None:
    """Reinicia el controlador de disco, la cola de E/S y la caché."""
    global _bloques_disco, _tam_bloque, _cache_bloques, _posicion_cabezal
    global _direccion_cabezal, _desplazamiento_total, _solicitudes_atendidas
    global _cola, _solicitud_activa, _siguiente_id, _reloj_ref
    global _cache, _cache_aciertos, _cache_fallos

    _bloques_disco = max(1, int(bloques_disco))
    _tam_bloque = max(1, int(tam_bloque))
    _cache_bloques = max(0, int(cache_bloques))

    _posicion_cabezal = 0
    _direccion_cabezal = 1
    _desplazamiento_total = 0
    _solicitudes_atendidas = 0
    _cola = []
    _solicitud_activa = None
    _siguiente_id = 1
    _reloj_ref = 0

    _cache = []
    _cache_aciertos = 0
    _cache_fallos = 0


def _sincronizar_reloj(reloj: int) -> None:
    """Actualiza la referencia de reloj discreto dentro del módulo de disco."""
    global _reloj_ref
    _reloj_ref = reloj


def _actualizar_cache(bloque: int) -> None:
    """Inserta o refresca un bloque en la caché LRU."""
    if _cache_bloques <= 0:
        return
    if bloque in _cache:
        _cache.remove(bloque)
    elif len(_cache) >= _cache_bloques:
        _cache.pop(0)
    _cache.append(bloque)


def _ordenar_indices_look(pendientes: list[dict], pos_inicial: int, dir_inicial: int) -> list[int]:
    """Calcula el orden de atención LOOK (SCAN sin recorrido vacío) con límite de espera."""
    if not pendientes:
        return []

    # Priorizar solicitudes con espera prolongada para evitar inanición (< 200 ticks)
    urgentes = [
        idx
        for idx, req in enumerate(pendientes)
        if (_reloj_ref - req["tick_llegada"]) >= _UMBRAL_ENVEJECIMIENTO_DISCO
    ]
    urgentes.sort(key=lambda i: (pendientes[i]["tick_llegada"], abs(pendientes[i]["bloque"] - pos_inicial)))

    restantes = [idx for idx in range(len(pendientes)) if idx not in urgentes]
    if not restantes:
        return urgentes

    pos_actual = urgentes[-1] if urgentes else None
    cabezal = pendientes[pos_actual]["bloque"] if pos_actual is not None else pos_inicial

    bloques_restantes = [pendientes[i]["bloque"] for i in restantes]
    min_b = min(bloques_restantes)
    max_b = max(bloques_restantes)

    # Elegir dirección hacia el extremo más cercano para minimizar desplazamiento total
    if abs(cabezal - min_b) <= abs(max_b - cabezal):
        direccion = -1
    else:
        direccion = 1

    arriba = sorted(
        [i for i in restantes if pendientes[i]["bloque"] >= cabezal],
        key=lambda i: (pendientes[i]["bloque"], pendientes[i]["id"]),
    )
    abajo = sorted(
        [i for i in restantes if pendientes[i]["bloque"] < cabezal],
        key=lambda i: (-pendientes[i]["bloque"], pendientes[i]["id"]),
    )

    if direccion >= 0:
        recorrido = arriba + abajo
    else:
        recorrido = abajo + arriba

    return urgentes + recorrido


def encolar_solicitud_disco(pid: int, bloque: int, operacion: str = "L") -> int:
    """Encola una solicitud de lectura ('L') o escritura ('E') y devuelve su ID único."""
    global _siguiente_id

    blk = int(bloque)
    op = str(operacion).upper()
    if blk < 0 or blk >= _bloques_disco:
        raise ErrorSistema(f"Bloque de disco {blk} fuera de rango [0, {_bloques_disco - 1}].")
    if op not in ("L", "E"):
        raise ErrorSistema(f"Operación de disco inválida: {operacion}. Use 'L' o 'E'.")

    sid = _siguiente_id
    _siguiente_id += 1
    _cola.append(
        {
            "id": sid,
            "pid": int(pid),
            "bloque": blk,
            "operacion": op,
            "tick_llegada": _reloj_ref,
        }
    )
    return sid


def _ejecutar_solicitud_inmediata(req: dict) -> int:
    """Atiende una solicitud de disco, actualiza métricas/caché y devuelve ticks de servicio."""
    global _posicion_cabezal, _direccion_cabezal, _desplazamiento_total
    global _solicitudes_atendidas, _cache_aciertos, _cache_fallos

    bloque = req["bloque"]
    op = req["operacion"]
    _solicitudes_atendidas += 1

    if op == "L" and bloque in _cache:
        _cache_aciertos += 1
        _actualizar_cache(bloque)
        return 1

    _cache_fallos += 1
    distancia = abs(_posicion_cabezal - bloque)
    if bloque > _posicion_cabezal:
        _direccion_cabezal = 1
    elif bloque < _posicion_cabezal:
        _direccion_cabezal = -1

    _desplazamiento_total += distancia
    _posicion_cabezal = bloque
    _actualizar_cache(bloque)
    return 1 + (distancia // 10)


def cola_disco() -> list:
    """Devuelve una copia de los bloques pendientes en el orden previsto de atención."""
    orden = _ordenar_indices_look(_cola, _posicion_cabezal, _direccion_cabezal)
    return [_cola[i]["bloque"] for i in orden]


def procesar_disco() -> list:
    """Atiende todas las solicitudes pendientes en la cola y devuelve el orden de bloques atendidos."""
    atendidos: list[int] = []
    while _cola:
        orden = _ordenar_indices_look(_cola, _posicion_cabezal, _direccion_cabezal)
        req = _cola.pop(orden[0])
        _ejecutar_solicitud_inmediata(req)
        atendidos.append(req["bloque"])
    return atendidos


def avanzar_tick_disco(reloj: int) -> None:
    """Paso de E/S en el reloj del kernel: avanza el servicio activo y despierta procesos listos."""
    global _solicitud_activa, _reloj_ref
    from . import procesos

    _reloj_ref = reloj

    if _solicitud_activa is None and _cola:
        orden = _ordenar_indices_look(_cola, _posicion_cabezal, _direccion_cabezal)
        req = _cola.pop(orden[0])
        ticks_servicio = _ejecutar_solicitud_inmediata(req)
        _solicitud_activa = {
            "pid": req["pid"],
            "bloque": req["bloque"],
            "ticks_restantes": ticks_servicio,
        }

    if _solicitud_activa is not None:
        _solicitud_activa["ticks_restantes"] -= 1
        if _solicitud_activa["ticks_restantes"] <= 0:
            pid_listo = _solicitud_activa["pid"]
            _solicitud_activa = None
            procesos.despertar_proceso(pid_listo)


def metricas_disco() -> dict:
    """Devuelve las métricas de desplazamiento y solicitudes atendidas del disco."""
    return {
        "solicitudes_atendidas": _solicitudes_atendidas,
        "desplazamiento_total": _desplazamiento_total,
        "posicion_cabezal": _posicion_cabezal,
    }


def info_cache() -> dict:
    """Devuelve estadísticas de aciertos y fallos de la caché de bloques."""
    total = _cache_aciertos + _cache_fallos
    tasa = (_cache_aciertos / total) if total > 0 else 0.0
    return {
        "capacidad_bloques": _cache_bloques,
        "aciertos": _cache_aciertos,
        "fallos": _cache_fallos,
        "tasa_aciertos": round(tasa, 4),
    }


def politica_disco() -> str:
    """Nombre del algoritmo de planificación de disco implementado."""
    return "LOOK (SCAN optimizado con envejecimiento)"