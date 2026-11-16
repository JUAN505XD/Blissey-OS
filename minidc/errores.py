"""Jerarquía de excepciones del sistema operativo simulado NimbusDC."""


class ErrorSistema(Exception):
    """Excepción base para todos los errores controlados de NimbusDC."""


class ErrorPermiso(ErrorSistema):
    """Se lanza cuando un usuario no tiene permisos para realizar una operación."""


class ErrorNoExiste(ErrorSistema):
    """Se lanza cuando un proceso, archivo, ruta o recurso solicitado no existe."""


class ErrorYaExiste(ErrorSistema):
    """Se lanza cuando se intenta crear un recurso con un identificador o ruta ya existente."""


class ErrorMemoria(ErrorSistema):
    """Se lanza ante accesos inválidos o falta de capacidad en memoria."""


class ErrorSincronizacion(ErrorSistema):
    """Se lanza ante operaciones inválidas sobre semáforos o mutex."""