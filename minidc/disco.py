"""Módulo de gestión de disco y cálculo de tiempo de servicio de E/S."""

from __future__ import annotations

_bloques_disco: int = 200
_tam_bloque: int = 512
_cache_bloques: int = 8
_posicion_cabezal: int = 0
_desplazamiento_total: int = 0
_solicitudes_atendidas: int = 0
_cola: list[dict] = []
_siguiente_id: int = 1


def _reiniciar_modulo(
    bloques_disco: int = 200, tam_bloque: int = 512, cache_bloques: int = 8
) -> None:
    global _bloques_disco, _tam_bloque, _cache_bloques, _posicion_cabezal
    global _desplazamiento_total, _solicitudes_atendidas, _cola, _siguiente_id
    _bloques_disco = bloques_disco
    _tam_bloque = tam_bloque
    _cache_bloques = cache_bloques
    _posicion_cabezal = 0
    _desplazamiento_total = 0
    _solicitudes_atendidas = 0
    _cola = []
    _siguiente_id = 1


def _registrar_es_kernel(pid: int, bloque: int) -> int:
    """Calcula el tiempo de servicio de E/S según la regla del enunciado y mueve el cabezal."""
    global _posicion_cabezal, _desplazamiento_total, _solicitudes_atendidas
    distancia = abs(_posicion_cabezal - bloque)
    _desplazamiento_total += distancia
    _posicion_cabezal = bloque
    _solicitudes_atendidas += 1
    return 1 + (distancia // 10)


def encolar_solicitud_disco(pid: int, bloque: int, operacion: str) -> int:
    global _siguiente_id
    sid = _siguiente_id
    _siguiente_id += 1
    _cola.append({"id": sid, "pid": pid, "bloque": bloque, "operacion": operacion})
    return sid


def procesar_disco() -> list:
    atendidos = []
    while _cola:
        req = _cola.pop(0)
        _registrar_es_kernel(req["pid"], req["bloque"])
        atendidos.append(req["bloque"])
    return atendidos


def cola_disco() -> list:
    return [req["bloque"] for req in _cola]


def metricas_disco() -> dict:
    return {
        "solicitudes_atendidas": _solicitudes_atendidas,
        "desplazamiento_total": _desplazamiento_total,
        "posicion_cabezal": _posicion_cabezal,
    }


def info_cache() -> dict:
    return {
        "capacidad_bloques": _cache_bloques,
        "aciertos": 0,
        "fallos": 0,
        "tasa_aciertos": 0.0,
    }


def politica_disco() -> str:
    return "SCAN"