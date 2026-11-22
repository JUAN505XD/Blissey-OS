"""Intérprete de comandos completo para Blissey OS (Prototipo 2)."""

from __future__ import annotations

import shlex

from . import archivos, disco, kernel, memoria, procesos
from .errores import ErrorNoExiste, ErrorSistema

_directorios_usuario: dict[str, str] = {"admin": "/"}
_historiales_usuario: dict[str, list[str]] = {"admin": []}


def _reiniciar_modulo() -> None:
    """Reinicia directorios independientes por usuario e historiales de comandos."""
    global _directorios_usuario, _historiales_usuario
    _directorios_usuario = {"admin": "/"}
    _historiales_usuario = {"admin": []}


def _registrar_directorio_usuario(usuario: str) -> str:
    """Asigna una ubicación independiente para cada usuario."""
    if usuario not in _directorios_usuario:
        if usuario == "admin":
            _directorios_usuario[usuario] = "/"
        else:
            try:
                archivos._buscar_nodo(f"/home/{usuario}", seguir_ultimo_enlace=True)
                _directorios_usuario[usuario] = f"/home/{usuario}"
            except ErrorSistema:
                _directorios_usuario[usuario] = "/"
    return _directorios_usuario[usuario]


def directorio_actual(usuario: str = "admin") -> str:
    """Devuelve el directorio de trabajo actual del usuario."""
    return _registrar_directorio_usuario(usuario)


def historial(usuario: str = "admin") -> list:
    """Devuelve una copia del historial de comandos ejecutados por el usuario."""
    return list(_historiales_usuario.setdefault(usuario, []))


def _resolver_ruta(ruta: str, usuario: str) -> str:
    """Convierte una ruta relativa o absoluta en una ruta normalizada absoluta."""
    base = directorio_actual(usuario)
    if ruta.startswith("/"):
        cruda = ruta
    else:
        cruda = f"{base.rstrip('/')}/{ruta}"

    partes: list[str] = []
    for p in cruda.split("/"):
        if not p or p == ".":
            continue
        if p == "..":
            if partes:
                partes.pop()
        else:
            partes.append(p)
    return "/" + "/".join(partes)


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
    """Construye una instantánea del monitor de urgencias y recursos."""
    res = kernel.resumen_sistema()
    met = procesos.metricas_planificacion()
    encabezado = (
        f"Blissey OS Urgencias | Reloj: {res['reloj']} | "
        f"Activos: {res['procesos_activos']} | "
        f"Terminados: {met['procesos_terminados']} | "
        f"Utilización CPU: {met['utilizacion_cpu'] * 100:.1f}% | "
        f"Marcos libres: {res['marcos_libres']} | "
        f"Bloques libres: {res['bloques_libres']}"
    )
    return f"{encabezado}\n{_formatear_ps()}"


def _construir_arbol(ruta: str, usuario: str, prefijo: str = "") -> list[str]:
    """Construye las líneas del comando tree recursivamente."""
    entradas = archivos.fs_listar(ruta, usuario)
    lineas: list[str] = []
    for idx, nombre in enumerate(entradas):
        es_ultimo = idx == len(entradas) - 1
        conector = "└── " if es_ultimo else "├── "
        ruta_hijo = f"{ruta.rstrip('/')}/{nombre}"
        info = archivos.fs_info(ruta_hijo)
        etiqueta = f"{nombre}/" if info["tipo"] == "directorio" else nombre
        lineas.append(f"{prefijo}{conector}{etiqueta}")
        if info["tipo"] == "directorio":
            ext = "    " if es_ultimo else "│   "
            lineas.extend(_construir_arbol(ruta_hijo, usuario, prefijo + ext))
    return lineas


def _manejar_echo(tokens: list[str], usuario: str) -> str:
    """Procesa 'echo texto > archivo' y 'echo texto >> archivo'."""
    if ">>" in tokens:
        idx = tokens.index(">>")
        agregar = True
    elif ">" in tokens:
        idx = tokens.index(">")
        agregar = False
    else:
        return " ".join(tokens[1:])

    if idx + 1 >= len(tokens):
        raise ErrorSistema("Falta la ruta de archivo destino en redirección echo.")

    texto = " ".join(tokens[1:idx])
    destino = _resolver_ruta(tokens[idx + 1], usuario)
    escritos = archivos.fs_escribir(destino, texto, usuario, agregar=agregar)
    return f"{escritos} bytes escritos en {destino}."


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

        # --- Comandos de Archivos ---
        if cmd == "pwd":
            return directorio_actual(usuario)

        if cmd == "cd":
            destino_raw = args[0] if args else ("/" if usuario == "admin" else f"/home/{usuario}")
            ruta_obj = _resolver_ruta(destino_raw, usuario)
            ruta_validada = archivos._validar_acceso_directorio(ruta_obj, usuario)
            _directorios_usuario[usuario] = ruta_validada
            return ruta_validada

        if cmd in ("ls", "dir"):
            detallado = "-l" in args
            rutas_args = [a for a in args if a != "-l"]
            ruta_obj = _resolver_ruta(rutas_args[0], usuario) if rutas_args else directorio_actual(usuario)
            entradas = archivos.fs_listar(ruta_obj, usuario)
            if not detallado:
                return "\n".join(entradas)
            lineas = []
            for nombre in entradas:
                ruta_item = f"{ruta_obj.rstrip('/')}/{nombre}" if ruta_obj != ruta_obj.rstrip("/") + "/" + nombre else ruta_obj
                info = archivos.fs_info(ruta_item)
                lineas.append(
                    f"{info['tipo'][0]} {info['modo']} {info['propietario']} "
                    f"{info['grupo']} {info['tamano']} {nombre}"
                )
            return "\n".join(lineas)

        if cmd in ("mkdir", "md"):
            if len(args) != 1:
                raise ErrorSistema(f"Uso: {cmd} RUTA")
            archivos.fs_mkdir(_resolver_ruta(args[0], usuario), usuario)
            return f"Directorio creado: {args[0]}"

        if cmd == "touch":
            if len(args) != 1:
                raise ErrorSistema("Uso: touch ARCHIVO")
            archivos.fs_escribir(_resolver_ruta(args[0], usuario), "", usuario, agregar=True)
            return f"Archivo actualizado: {args[0]}"

        if cmd in ("cat", "type"):
            if len(args) != 1:
                raise ErrorSistema(f"Uso: {cmd} ARCHIVO")
            return archivos.fs_leer(_resolver_ruta(args[0], usuario), usuario)

        if cmd == "echo":
            return _manejar_echo(tokens, usuario)

        if cmd in ("rm", "del"):
            recursivo = any(a in ("-r", "-rf", "-fr") for a in args)
            objetivos = [a for a in args if not a.startswith("-")]
            if len(objetivos) != 1:
                raise ErrorSistema(f"Uso: {cmd} [-r] RUTA")
            archivos.fs_eliminar(_resolver_ruta(objetivos[0], usuario), usuario, recursivo=recursivo)
            return f"Eliminado: {objetivos[0]}"

        if cmd == "chmod":
            if len(args) != 2:
                raise ErrorSistema("Uso: chmod MODO RUTA")
            archivos.fs_chmod(_resolver_ruta(args[1], usuario), args[0], usuario)
            return f"Permisos de {args[1]} actualizados a {args[0]}."

        if cmd in ("ln", "mklink"):
            if cmd == "ln":
                if len(args) != 3 or args[0] != "-s":
                    raise ErrorSistema("Uso: ln -s DESTINO ENLACE")
                destino, ruta_enlace = args[1], _resolver_ruta(args[2], usuario)
            else:
                if len(args) != 2:
                    raise ErrorSistema("Uso: mklink ENLACE DESTINO")
                ruta_enlace, destino = _resolver_ruta(args[0], usuario), args[1]
            archivos.fs_enlace_simbolico(destino, ruta_enlace, usuario)
            return f"Enlace creado: {ruta_enlace} -> {destino}"

        if cmd == "tree":
            ruta_obj = _resolver_ruta(args[0], usuario) if args else directorio_actual(usuario)
            cabecera = ruta_obj
            cuerpo = _construir_arbol(ruta_obj, usuario)
            return "\n".join([cabecera] + cuerpo)

        # --- Comandos de Procesos ---
        if cmd in ("ps", "tasklist"):
            return _formatear_ps()

        if cmd in ("run", "admitir"):
            if len(args) != 1:
                raise ErrorSistema(f"Uso: {cmd} NOMBRE")
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

        # --- Comandos de Recursos ---
        if cmd == "free":
            est = memoria.estado_memoria()
            met = memoria.metricas_memoria()
            return (
                f"Marcos totales: {est['marcos_totales']} | "
                f"Libres: {est['marcos_libres']} | "
                f"Frag. interna: {est['fragmentacion_interna_bytes']} B | "
                f"Tasa fallos: {met['tasa_fallos'] * 100:.1f}%"
            )

        if cmd == "df":
            est = archivos.fs_estado_disco()
            met_d = disco.metricas_disco()
            return (
                f"Bloques totales: {est['bloques_totales']} | "
                f"Libres: {est['bloques_libres']} | "
                f"Huecos: {est['huecos_libres']} | "
                f"Política FS: {archivos.politica_asignacion_archivos()} | "
                f"Cabezal disco: {met_d['posicion_cabezal']}"
            )

        if cmd == "whoami":
            return usuario

        raise ErrorNoExiste(f"Comando no reconocido: {cmd}")

    except ErrorSistema as exc:
        return f"Error: {exc}"