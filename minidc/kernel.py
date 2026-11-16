"""Núcleo y reloj discreto del sistema operativo simulado NimbusDC."""

from __future__ import annotations

import json
from pathlib import Path

from . import archivos, consola, disco, memoria, procesos, sincronizacion
from .errores import ErrorNoExiste, ErrorSistema

_CONFIG_DEFECTO = {
    "num_cpus": 1,
    "marcos_fisicos": 16,
    "tam_pagina": 256,
    "bloques_disco": 200,
    "tam_bloque": 512,
    "cache_bloques": 8,
}

_reloj: int = 0
_config_actual: dict = dict(_CONFIG_DEFECTO)
_catalogo_escenario: dict[str, dict] = {}
_llegadas_programadas: dict[int, list[dict]] = {}
_sistema_iniciado: bool = False


def iniciar_sistema(config: dict) -> None:
    """Inicializa o reinicia por completo el estado de todos los módulos del sistema."""
    global _reloj, _config_actual, _catalogo_escenario, _llegadas_programadas, _sistema_iniciado

    cfg = dict(_CONFIG_DEFECTO)
    if config:
        cfg.update(config)

    _reloj = 0
    _config_actual = cfg
    _catalogo_escenario = {}
    _llegadas_programadas = {}
    _sistema_iniciado = True

    procesos._reiniciar_modulo(num_cpus=int(cfg["num_cpus"]))
    memoria._reiniciar_modulo(
        marcos_fisicos=int(cfg["marcos_fisicos"]),
        tam_pagina=int(cfg["tam_pagina"]),
    )
    disco._reiniciar_modulo(
        bloques_disco=int(cfg["bloques_disco"]),
        tam_bloque=int(cfg["tam_bloque"]),
        cache_bloques=int(cfg["cache_bloques"]),
    )
    archivos._reiniciar_modulo(bloques_disco=int(cfg["bloques_disco"]))
    sincronizacion._reiniciar_modulo()
    consola._reiniciar_modulo()


def _procesar_llegadas_hasta(tick_objetivo: int) -> None:
    """Admite los procesos programados en el escenario cuya llegada sea <= tick_objetivo."""
    tickets_pendientes = [t for t in sorted(_llegadas_programadas.keys()) if t <= tick_objetivo]
    for t in tickets_pendientes:
        eventos = _llegadas_programadas.pop(t)
        for ev in eventos:
            nombre_prog = ev["programa"]
            usuario = ev.get("usuario", "admin")
            ejecutar_desde_catalogo(nombre_prog, usuario=usuario)


def ejecutar_desde_catalogo(nombre_programa: str, usuario: str = "admin") -> int:
    """Instancia un proceso tomando su definición del catálogo cargado en el escenario."""
    if nombre_programa not in _catalogo_escenario:
        raise ErrorNoExiste(f"El programa '{nombre_programa}' no existe en el catálogo.")

    spec = _catalogo_escenario[nombre_programa]
    memoria_bytes = int(spec.get("memoria_bytes", spec.get("memoria bytes", 4096)))
    cuota_marcos = int(spec.get("cuota_marcos", spec.get("cuota marcos", 4)))
    prioridad = int(spec.get("prioridad", 0))
    programa = spec.get("programa", [])

    return procesos.crear_proceso(
        nombre=nombre_programa,
        usuario=usuario,
        programa=programa,
        memoria_bytes=memoria_bytes,
        cuota_marcos=cuota_marcos,
        prioridad=prioridad,
    )


def cargar_escenario(ruta_json: str) -> None:
    """Carga un archivo JSON de escenario, reinicia el kernel y programa las llegadas."""
    global _catalogo_escenario, _llegadas_programadas

    ruta = Path(ruta_json)
    if not ruta.exists():
        raise ErrorNoExiste(f"El archivo de escenario no existe: {ruta_json}")

    with ruta.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    iniciar_sistema(datos.get("config", {}))

    for usuario in datos.get("usuarios", []):
        if usuario != "admin":
            archivos.crear_usuario(usuario)

    for nombre_sem, valor in datos.get("semaforos", {}).items():
        sincronizacion.crear_semaforo(nombre_sem, int(valor))

    _catalogo_escenario = dict(datos.get("catalogo", {}))
    _llegadas_programadas = {}
    for llegada in datos.get("llegadas", []):
        t = int(llegada["tick"])
        _llegadas_programadas.setdefault(t, []).append(dict(llegada))

    # Admitir procesos programados en tick 0 desde la carga inicial
    _procesar_llegadas_hasta(0)


def tick() -> None:
    """Avanza el reloj discreto en 1 unidad y ejecuta el ciclo determinista del kernel."""
    global _reloj

    if not _sistema_iniciado:
        iniciar_sistema({})

    # 1. Avance del reloj
    _reloj += 1
    procesos._sincronizar_reloj(_reloj)

    # 2. Llegada de procesos programados en el escenario
    _procesar_llegadas_hasta(_reloj)

    # 3. Atención de E/S terminada y desbloqueos (interrupciones)
    procesos.procesar_interrupciones_bloqueo()

    # 4. Planificación y ejecución de 1 tick por cada CPU
    procesos.ejecutar_ciclo_cpus(_reloj)


def ejecutar_ticks(n: int) -> None:
    """Ejecuta n ciclos consecutivos de tick()."""
    if n < 0:
        raise ErrorSistema("La cantidad de ticks a ejecutar no puede ser negativa.")
    for _ in range(n):
        tick()


def reloj_actual() -> int:
    """Devuelve el valor actual del reloj discreto."""
    return _reloj


def resumen_sistema() -> dict:
    """Devuelve un resumen instantáneo del estado global del servidor simulado."""
    estado_mem = memoria.estado_memoria()
    estado_fs = archivos.fs_estado_disco()
    return {
        "reloj": _reloj,
        "procesos_activos": procesos._contar_activos(),
        "marcos_libres": estado_mem["marcos_libres"],
        "bloques_libres": estado_fs["bloques_libres"],
    }


def apagar_sistema() -> dict:
    """Genera el resumen final de ejecución y detiene la simulación activa."""
    global _sistema_iniciado
    resumen = resumen_sistema()
    resumen["metricas_planificacion"] = procesos.metricas_planificacion()
    _sistema_iniciado = False
    return resumen