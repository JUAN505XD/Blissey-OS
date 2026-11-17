"""Intérprete de comandos de administración de urgencias para Blissey OS."""

from __future__ import annotations

import shlex

from . import archivos, kernel, memoria, procesos
from .errores import ErrorNoExiste, ErrorSistema

_directorios_usuario: dict[str, str] = {"admin": "/"}
_historiales_usuario: dict[str, list[str]] = {"admin": []}


def _reiniciar_modulo() -> None:
    """Reinicia directorios independientes por usuario e historiales de comandos."""
    global _directorios_usuario, _historiales_usuario
    _directorios_usuario = {"admin": "/"}
    _historiales_usuario = {"admin": []}


def _registrar_directorio_usuario(usuario: str) -> str:
    """Asigna una ubicación independiente para cada usuario del hospital."""
    if usuario not in _directorios_usuario:
        _directorios_usuario[usuario] = "/" if usuario == "admin" else f"/home/{usuario}"
    return _directorios_usuario[usuario]


def directorio_actual(usuario: str = "admin") -> str:
    """Devuelve el directorio de trabajo actual del usuario."""
    return _registrar_directorio_usuario(usuario)


def historial(usuario: str = "admin") -> list:
    """Devuelve una copia del historial de comandos ejecutados por el usuario."""
    return list(_historiales_usuario.setdefault(usuario, []))


def _formatear_ps() -> str:
    """Formatea la tabla de procesos/pacientes comenzando con la cabecera obligatoria."""
    lineas = ["PID NOMBRE USUARIO ESTADO PRIORIDAD CPU_USADA ESPERA"]
    for p in procesos.listar_procesos():
        lineas.append(
            f"{p['pid']} {p['nombre']} {p['usuario']} {p['estado']} "
            f"{p['prioridad']} {p['cpu_usada']} {p['tiempo_espera']}"
        )
    return "\n".join(lineas)


def _formatear_top() -> str:
    """Construye una instantánea del monitor de urgencias y utilización de recursos."""
    res = kernel.resumen_sistema()
    met = procesos.metricas_planificacion()
    encabezado = (
        f"Blissey OS Urgencias | Reloj: {res['reloj']} | "
        f"En atención/espera: {res['procesos_activos']} | "
        f"Atendidos (alta): {met['procesos_terminados']} | "
        f"Utilización CPU: {met['utilizacion_cpu'] * 100:.1f}% | "
        f"Respuesta web prom: {met['respuesta_promedio_web']:.2f} | "
        f"Espera máx: {met['espera_maxima']}"
    )
    return f"{encabezado}\n{_formatear_ps()}"


def ejecutar_comando(linea: str, usuario: str = "admin") -> str:
    """Ejecuta un comando de consola y captura excepciones devolviendo texto con prefijo Error:."""
    texto = linea.strip()
    _registrar_directorio_usuario(usuario)
    _historiales_usuario.setdefault(usuario, []).append(texto)

    if not texto:
        return ""

    try:
        tokens = shlex.split(texto)
        cmd = tokens[0].lower()
        args = tokens[1:]

        if cmd in ("ps", "tasklist"):
            return _formatear_ps()

        if cmd in ("run", "admitir"):
            if len(args) == 1:
                pid = kernel.ejecutar_desde_catalogo(args[0], usuario=usuario)
                return f"Admisión '{args[0]}' registrada con PID {pid}."
            if len(args) in (2, 3):
                try:
                    rafaga = int(args[1])
                    prioridad = int(args[2]) if len(args) == 3 else 1
                except ValueError as exc:
                    raise ErrorSistema(f"Parámetros numéricos inválidos en {cmd}.") from exc
                if rafaga <= 0:
                    raise ErrorSistema("La ráfaga de CPU debe ser mayor que 0.")
                pid = procesos.crear_proceso(
                    nombre=args[0],
                    usuario=usuario,
                    programa=[["CPU", rafaga]],
                    prioridad=prioridad,
                )
                return f"Proceso '{args[0]}' creado con PID {pid}."
            raise ErrorSistema(f"Uso: {cmd} NOMBRE [RAFAGA_CPU] [PRIORIDAD]")

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