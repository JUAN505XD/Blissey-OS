"""Intérprete de comandos de administración para NimbusDC."""

from __future__ import annotations

import shlex

from . import archivos, disco, kernel, memoria, procesos
from .errores import ErrorNoExiste, ErrorSistema

_directorios_usuario: dict[str, str] = {"admin": "/"}
_historiales_usuario: dict[str, list[str]] = {"admin": []}


def _reiniciar_modulo() -> None:
    """Reinicia directorios actuales e historiales de comandos."""
    global _directorios_usuario, _historiales_usuario
    _directorios_usuario = {"admin": "/"}
    _historiales_usuario = {"admin": []}


def directorio_actual(usuario: str = "admin") -> str:
    """Devuelve el directorio de trabajo actual del usuario."""
    return _directorios_usuario.setdefault(usuario, "/")


def historial(usuario: str = "admin") -> list:
    """Devuelve una copia del historial de comandos ejecutados por el usuario."""
    return list(_historiales_usuario.setdefault(usuario, []))


def _formatear_ps() -> str:
    """Formatea la tabla de procesos comenzando con la cabecera obligatoria."""
    lineas = ["PID NOMBRE USUARIO ESTADO PRIORIDAD CPU_USADA ESPERA"]
    for p in procesos.listar_procesos():
        lineas.append(
            f"{p['pid']} {p['nombre']} {p['usuario']} {p['estado']} "
            f"{p['prioridad']} {p['cpu_usada']} {p['tiempo_espera']}"
        )
    return "\n".join(lineas)


def _formatear_top() -> str:
    """Construye una instantánea completa del estado de CPU y procesos."""
    res = kernel.resumen_sistema()
    met = procesos.metricas_planificacion()
    encabezado = (
        f"NimbusDC TOP | Reloj: {res['reloj']} | "
        f"Activos: {res['procesos_activos']} | "
        f"Terminados: {met['procesos_terminados']} | "
        f"Utilización CPU: {met['utilizacion_cpu'] * 100:.1f}% | "
        f"Respuesta prom: {met['respuesta_promedio']:.2f} | "
        f"Espera máx: {met['espera_maxima']}"
    )
    return f"{encabezado}\n{_formatear_ps()}"


def ejecutar_comando(linea: str, usuario: str = "admin") -> str:
    """Ejecuta un comando de consola y captura excepciones devolviendo texto con prefijo Error:."""
    texto = linea.strip()
    _historiales_usuario.setdefault(usuario, []).append(texto)

    if not texto:
        return ""

    try:
        tokens = shlex.split(texto)
        cmd = tokens[0].lower()
        args = tokens[1:]

        if cmd in ("ps", "tasklist"):
            return _formatear_ps()

        if cmd == "run":
            if len(args) != 1:
                raise ErrorSistema("Uso: run NOMBRE")
            pid = kernel.ejecutar_desde_catalogo(args[0], usuario=usuario)
            return f"Proceso '{args[0]}' iniciado con PID {pid}."

        if cmd in ("kill", "taskkill"):
            if len(args) != 1:
                raise ErrorSistema("Uso: kill PID")
            try:
                pid = int(args[0])
            except ValueError as exc:
                raise ErrorSistema(f"PID inválido: {args[0]}") from exc
            procesos.terminar_proceso(pid)
            return f"Proceso {pid} terminado."

        if cmd == "tick":
            if len(args) == 0:
                n = 1
            elif len(args) == 1:
                try:
                    n = int(args[0])
                except ValueError as exc:
                    raise ErrorSistema(f"Cantidad de ticks inválida: {args[0]}") from exc
            else:
                raise ErrorSistema("Uso: tick [N]")
            kernel.ejecutar_ticks(n)
            return f"Reloj avanzado a tick {kernel.reloj_actual()}."

        if cmd == "top":
            return _formatear_top()

        if cmd == "whoami":
            return usuario

        if cmd == "pwd":
            return directorio_actual(usuario)

        if cmd == "free":
            est = memoria.estado_memoria()
            return (
                f"Marcos totales: {est['marcos_totales']} | "
                f"Libres: {est['marcos_libres']}"
            )

        if cmd == "df":
            est = archivos.fs_estado_disco()
            return (
                f"Bloques totales: {est['bloques_totales']} | "
                f"Libres: {est['bloques_libres']}"
            )

        raise ErrorNoExiste(f"Comando no reconocido: {cmd}")

    except ErrorSistema as exc:
        return f"Error: {exc}"