"""Módulo base de sistema de archivos y usuarios."""

from __future__ import annotations

_bloques_totales: int = 200
_usuarios: dict[str, str] = {"admin": "admin"}


def _reiniciar_modulo(bloques_disco: int = 200) -> None:
    global _bloques_totales, _usuarios
    _bloques_totales = bloques_disco
    _usuarios = {"admin": "admin"}


def formatear_disco() -> None:
    _reiniciar_modulo(_bloques_totales)


def crear_usuario(nombre: str, grupo: str = "usuarios") -> None:
    _usuarios[nombre] = grupo


def fs_mkdir(ruta: str, usuario: str) -> None:
    pass


def fs_escribir(ruta: str, contenido: str, usuario: str, agregar: bool = False) -> int:
    return len(contenido.encode("utf-8"))


def fs_leer(ruta: str, usuario: str) -> str:
    return ""


def fs_listar(ruta: str, usuario: str) -> list:
    return []


def fs_eliminar(ruta: str, usuario: str, recursivo: bool = False) -> None:
    pass


def fs_chmod(ruta: str, modo: str, usuario: str) -> None:
    pass


def fs_enlace_simbolico(destino: str, ruta_enlace: str, usuario: str) -> None:
    pass


def fs_info(ruta: str) -> dict:
    return {
        "tipo": "directorio",
        "tamano": 0,
        "propietario": "admin",
        "grupo": "admin",
        "modo": "755",
        "bloques": [],
    }


def fs_estado_disco() -> dict:
    return {
        "bloques_totales": _bloques_totales,
        "bloques_libres": _bloques_totales,
        "huecos_libres": 1,
    }


def politica_asignacion_archivos() -> str:
    return "Indexada"