"""Jerarquía de excepciones, registro y disparadores de fallos de Blissey OS."""

from __future__ import annotations

from typing import NoReturn

_historial_errores: list[dict] = []


def _registrar_evento(tipo: str, detalle: str, pid: int | None = None) -> None:
    """Guarda un registro estructurado cada vez que se dispara una excepción del sistema."""
    _historial_errores.append(
        {
            "tipo": tipo,
            "pid": pid,
            "detalle": detalle,
        }
    )


def obtener_historial_errores() -> list[dict]:
    """Devuelve una copia de todos los fallos capturados por el subsistema de errores."""
    return list(_historial_errores)


def limpiar_historial_errores() -> None:
    """Limpia la bitácora interna de errores registrados."""
    _historial_errores.clear()


class ErrorSistema(Exception):
    """Excepción base para todos los errores controlados de Blissey OS."""

    def __init__(self, mensaje: str = "Error interno del sistema Blissey OS.") -> None:
        super().__init__(mensaje)


class ErrorPermiso(ErrorSistema):
    """Se lanza cuando un usuario no tiene permisos para realizar una operación (RF1)."""

    def __init__(self, mensaje: str = "Permiso denegado para realizar esta operación.") -> None:
        _registrar_evento("ErrorPermiso", mensaje)
        super().__init__(mensaje)


class ErrorNoExiste(ErrorSistema):
    """Se lanza cuando un proceso, archivo, ruta o recurso solicitado no existe."""

    def __init__(self, mensaje: str = "El recurso solicitado no existe.") -> None:
        _registrar_evento("ErrorNoExiste", mensaje)
        super().__init__(mensaje)


class ErrorYaExiste(ErrorSistema):
    """Se lanza cuando se intenta crear un recurso con un identificador o ruta ya existente."""

    def __init__(self, mensaje: str = "El recurso ya existe.") -> None:
        _registrar_evento("ErrorYaExiste", mensaje)
        super().__init__(mensaje)


class ErrorMemoria(ErrorSistema):
    """Excepción de segmentación o falta de marcos en memoria virtual (RM3)."""

    def __init__(
        self,
        mensaje: str | None = None,
        *,
        pid: int | None = None,
        direccion: int | None = None,
        limite: int | None = None,
    ) -> None:
        self.pid = pid
        self.direccion = direccion
        self.limite = limite

        if mensaje is None and pid is not None and direccion is not None and limite is not None:
            rango = f"[0, {limite - 1}]" if limite > 0 else "[sin memoria asignada]"
            mensaje = (
                f"[FALLO DE MEMORIA - RM3] PID {pid}: dirección virtual {direccion} "
                f"fuera de límites (espacio permitido: {rango}, asignado: {limite} B)."
            )
        elif mensaje is None:
            mensaje = "[FALLO DE MEMORIA - RM3] Acceso fuera del espacio de memoria virtual del proceso."

        _registrar_evento("ErrorMemoria", mensaje, pid=pid)
        super().__init__(mensaje)


class ErrorSincronizacion(ErrorSistema):
    """Se lanza ante operaciones inválidas sobre semáforos o mutex."""

    def __init__(self, mensaje: str = "Error en operación de sincronización.") -> None:
        _registrar_evento("ErrorSincronizacion", mensaje)
        super().__init__(mensaje)


def lanzar_error_memoria(pid: int, direccion: int, limite: int) -> NoReturn:
    """Construye, registra y lanza ErrorMemoria ante un acceso fuera del espacio virtual (RM3)."""
    raise ErrorMemoria(pid=pid, direccion=direccion, limite=limite)


def lanzar_error_sin_marcos(pid: int | None = None) -> NoReturn:
    """Registra y lanza ErrorMemoria cuando no existen marcos físicos disponibles."""
    detalle = (
        f"[FALLO DE MEMORIA - RM3] PID {pid}: no hay marcos físicos disponibles para asignar."
        if pid is not None
        else "[FALLO DE MEMORIA - RM3] No hay marcos físicos disponibles para asignar."
    )
    raise ErrorMemoria(detalle, pid=pid)