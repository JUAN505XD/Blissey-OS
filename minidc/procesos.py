"""Gestión de procesos, hilos múltiples y planificación por urgencia de Blissey OS (Prototipo 2)."""

from __future__ import annotations

from typing import Optional

from .errores import ErrorMemoria, ErrorNoExiste, ErrorSistema

ESTADOS_VALIDOS = ("NUEVO", "LISTO", "EJECUTANDO", "BLOQUEADO", "TERMINADO")

_QUANTUM_DEFECTO = 3
_INTERVALO_ENVEJECIMIENTO = 10
_UMBRAL_EMERGENCIA_INANICION = 100

_procesos: dict[int, dict] = {}
_cola_listos: list[int] = []
_cpus: list[Optional[int]] = [None]
_siguiente_pid: int = 1
_siguiente_tid: int = 1
_cambios_contexto: int = 0
_ticks_cpu_ocupados: int = 0
_reloj_ref: int = 0


def _reiniciar_modulo(num_cpus: int = 1) -> None:
    """Reinicia todas las estructuras internas del gestor de procesos."""
    global _procesos, _cola_listos, _cpus, _siguiente_pid, _siguiente_tid
    global _cambios_contexto, _ticks_cpu_ocupados, _reloj_ref

    if num_cpus < 1:
        raise ErrorSistema("El número de consultorios/CPUs debe ser al menos 1.")

    _procesos = {}
    _cola_listos = []
    _cpus = [None for _ in range(num_cpus)]
    _siguiente_pid = 1
    _siguiente_tid = 1
    _cambios_contexto = 0
    _ticks_cpu_ocupados = 0
    _reloj_ref = 0


def _sincronizar_reloj(reloj: int) -> None:
    """Actualiza el reloj interno conocido por el módulo de procesos."""
    global _reloj_ref
    _reloj_ref = reloj


def _normalizar_programa(programa: list) -> list[tuple]:
    """Convierte las instrucciones del programa a una lista de tuplas normalizadas."""
    resultado = []
    for inst in programa:
        if not isinstance(inst, (list, tuple)) or len(inst) < 2:
            raise ErrorSistema(f"Instrucción inválida en programa: {inst!r}")
        op = str(inst[0]).upper()
        arg = inst[1]
        if op in ("CPU", "ES", "MEM"):
            resultado.append((op, int(arg)))
        elif op in ("WAIT", "SIGNAL"):
            resultado.append((op, str(arg)))
        else:
            raise ErrorSistema(f"Código de operación desconocido: {op}")
    return resultado


def _crear_estructura_hilo(tid: int, programa: list) -> dict:
    prog_norm = _normalizar_programa(programa)
    inst_restante = prog_norm[0][1] if prog_norm and prog_norm[0][0] == "CPU" else 0
    return {
        "tid": tid,
        "programa": prog_norm,
        "ip": 0,
        "inst_restante": inst_restante,
        "estado": "LISTO" if prog_norm else "TERMINADO",
    }


def _clave_planificacion(pid: int) -> tuple:
    """Calcula la prioridad efectiva considerando urgencia (triage) y envejecimiento."""
    pcb = _procesos[pid]
    emergencia = 0 if pcb["espera_consecutiva"] >= _UMBRAL_EMERGENCIA_INANICION else 1
    prio_efectiva = pcb["prioridad"] + pcb["bono_envejecimiento"]
    primera_vez = 0 if pcb["primera_ejecucion"] is None else 1
    return (
        emergencia,
        -prio_efectiva,
        primera_vez,
        pcb["tick_llegada"],
        pcb["pid"],
    )


def _ordenar_cola_listos() -> None:
    """Ordena la cola de listos según urgencia efectiva."""
    _cola_listos.sort(key=_clave_planificacion)


def _obtener_pcb(pid: int) -> dict:
    if pid not in _procesos:
        raise ErrorNoExiste(f"El proceso con PID {pid} no existe.")
    return _procesos[pid]


def _cambiar_estado(pcb: dict, nuevo_estado: str) -> None:
    """Centraliza las transiciones de estado del proceso."""
    if nuevo_estado not in ESTADOS_VALIDOS:
        raise ErrorSistema(f"Estado de proceso inválido: {nuevo_estado}")
    estado_anterior = pcb["estado"]
    if estado_anterior == nuevo_estado:
        return

    pid = pcb["pid"]
    if estado_anterior == "LISTO" and pid in _cola_listos:
        _cola_listos.remove(pid)

    pcb["estado"] = nuevo_estado

    if nuevo_estado == "LISTO":
        pcb["quantum_usado"] = 0
        if pid not in _cola_listos:
            _cola_listos.append(pid)
        _ordenar_cola_listos()
    elif nuevo_estado == "EJECUTANDO":
        pcb["espera_consecutiva"] = 0
        pcb["bono_envejecimiento"] = 0
        pcb["quantum_usado"] = 0


def crear_proceso(
    nombre: str,
    usuario: str,
    programa: list,
    memoria_bytes: int = 4096,
    cuota_marcos: int = 4,
    prioridad: int = 0,
) -> int:
    """Crea un nuevo proceso con su hilo principal y lo pasa a estado LISTO."""
    global _siguiente_pid, _siguiente_tid

    pid = _siguiente_pid
    _siguiente_pid += 1

    tid_principal = _siguiente_tid
    _siguiente_tid += 1

    hilo_principal = _crear_estructura_hilo(tid_principal, programa)

    pcb = {
        "pid": pid,
        "nombre": str(nombre),
        "usuario": str(usuario),
        "memoria_bytes": int(memoria_bytes),
        "cuota_marcos": int(cuota_marcos),
        "prioridad": int(prioridad),
        "bono_envejecimiento": 0,
        "estado": "NUEVO",
        "tick_llegada": _reloj_ref,
        "primera_ejecucion": None,
        "tick_fin": None,
        "cpu_usada": 0,
        "tiempo_espera": 0,
        "espera_consecutiva": 0,
        "max_espera_consecutiva": 0,
        "quantum_usado": 0,
        "bloqueo_restante": 0,
        "motivo_bloqueo": None,
        "hilos": [hilo_principal],
        "indice_hilo_actual": 0,
    }
    _procesos[pid] = pcb

    if all(h["estado"] == "TERMINADO" for h in pcb["hilos"]):
        terminar_proceso(pid)
    else:
        _cambiar_estado(pcb, "LISTO")
    return pid


def crear_hilo(pid: int, programa: list) -> int:
    """Crea un hilo adicional dentro de un proceso existente y devuelve su TID."""
    global _siguiente_tid
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        raise ErrorSistema(f"No se pueden crear hilos en el proceso terminado {pid}.")

    tid = _siguiente_tid
    _siguiente_tid += 1
    nuevo_hilo = _crear_estructura_hilo(tid, programa)
    pcb["hilos"].append(nuevo_hilo)

    if pcb["estado"] == "BLOQUEADO" and pcb["motivo_bloqueo"] is None and nuevo_hilo["estado"] == "LISTO":
        _cambiar_estado(pcb, "LISTO")
    return tid


def _liberar_recursos_proceso(pid: int) -> None:
    """Libera memoria y recursos de sincronización asociados al proceso al terminar."""
    from . import memoria, sincronizacion

    memoria.liberar_memoria(pid)
    sincronizacion._liberar_recursos_pid(pid)


def terminar_proceso(pid: int) -> None:
    """Finaliza un proceso y todos sus hilos, liberando memoria y semáforos."""
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        return

    for idx, cpu_pid in enumerate(_cpus):
        if cpu_pid == pid:
            _cpus[idx] = None

    if pid in _cola_listos:
        _cola_listos.remove(pid)

    pcb["estado"] = "TERMINADO"
    pcb["tick_fin"] = _reloj_ref
    pcb["bloqueo_restante"] = 0
    pcb["motivo_bloqueo"] = None
    for hilo in pcb["hilos"]:
        hilo["estado"] = "TERMINADO"

    _liberar_recursos_proceso(pid)


def bloquear_proceso(pid: int, ticks_bloqueo: int = 0, motivo: str = "ES") -> None:
    """Pasa un proceso a estado BLOQUEADO por E/S de disco, fallo de página o sincronización."""
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        return

    for idx, cpu_pid in enumerate(_cpus):
        if cpu_pid == pid:
            _cpus[idx] = None

    pcb["bloqueo_restante"] = max(0, int(ticks_bloqueo))
    pcb["motivo_bloqueo"] = motivo
    _cambiar_estado(pcb, "BLOQUEADO")


def despertar_proceso(pid: int) -> None:
    """Reincorpora un proceso BLOQUEADO a la cola de LISTO."""
    if pid not in _procesos:
        return
    pcb = _procesos[pid]
    if pcb["estado"] == "BLOQUEADO":
        pcb["bloqueo_restante"] = 0
        pcb["motivo_bloqueo"] = None
        for hilo in pcb["hilos"]:
            if hilo["estado"] == "BLOQUEADO":
                hilo["estado"] = "LISTO"
        _cambiar_estado(pcb, "LISTO")


def procesar_interrupciones_bloqueo() -> None:
    """Actualiza temporizadores de bloqueo por fallo de página (5 ticks) y despierta procesos."""
    for pcb in list(_procesos.values()):
        if pcb["estado"] == "BLOQUEADO" and pcb["bloqueo_restante"] > 0:
            pcb["bloqueo_restante"] -= 1
            if pcb["bloqueo_restante"] == 0:
                despertar_proceso(pcb["pid"])


def _seleccionar_hilo_ejecutable(pcb: dict) -> Optional[dict]:
    """Selecciona el siguiente hilo listo del proceso en orden circular (Round-Robin interno)."""
    hilos = pcb["hilos"]
    total = len(hilos)
    inicio = pcb["indice_hilo_actual"] % total
    for offset in range(total):
        idx = (inicio + offset) % total
        hilo = hilos[idx]
        if hilo["estado"] == "LISTO":
            pcb["indice_hilo_actual"] = (idx + 1) % total
            return hilo
    return None


def _avanzar_instrucciones_hilo(pcb: dict, hilo: dict) -> None:
    """Ejecuta instrucciones no bloqueantes del hilo o inicia bloqueo por E/S o fallo de página."""
    from . import disco, memoria

    while pcb["estado"] != "TERMINADO" and hilo["ip"] < len(hilo["programa"]):
        op, arg = hilo["programa"][hilo["ip"]]
        if op == "CPU":
            if hilo["inst_restante"] <= 0:
                hilo["inst_restante"] = int(arg)
            if hilo["inst_restante"] > 0:
                return
            hilo["ip"] += 1
        elif op == "ES":
            hilo["ip"] += 1
            hilo["estado"] = "BLOQUEADO"
            disco.encolar_solicitud_disco(pcb["pid"], int(arg), "L")
            bloquear_proceso(pcb["pid"], ticks_bloqueo=0, motivo="ES")
            return
        elif op == "MEM":
            hilo["ip"] += 1
            try:
                res = memoria.acceder_memoria(pcb["pid"], int(arg))
            except ErrorMemoria:
                terminar_proceso(pcb["pid"])
                return
            if res.get("fallo_pagina", False):
                hilo["estado"] = "BLOQUEADO"
                bloquear_proceso(pcb["pid"], ticks_bloqueo=5, motivo="MEM")
                return
        elif op in ("WAIT", "SIGNAL"):
            hilo["ip"] += 1
        else:
            hilo["ip"] += 1

    if hilo["ip"] >= len(hilo["programa"]):
        hilo["estado"] = "TERMINADO"

    if all(h["estado"] == "TERMINADO" for h in pcb["hilos"]) and pcb["estado"] != "TERMINADO":
        terminar_proceso(pcb["pid"])


def planificar_cpus(reloj: int) -> None:
    """Evalúa apropiación por urgencia/quantum y asigna procesos a las CPUs libres."""
    global _cambios_contexto, _reloj_ref
    _reloj_ref = reloj

    _ordenar_cola_listos()

    for cpu_idx in range(len(_cpus)):
        pid_actual = _cpus[cpu_idx]
        if pid_actual is None:
            continue

        pcb_actual = _procesos.get(pid_actual)
        if pcb_actual is None or pcb_actual["estado"] != "EJECUTANDO":
            _cpus[cpu_idx] = None
            continue

        if _cola_listos:
            mejor_candidato = _cola_listos[0]
            clave_candidato = _clave_planificacion(mejor_candidato)
            clave_actual = _clave_planificacion(pid_actual)

            if clave_candidato[:2] < clave_actual[:2] or (
                pcb_actual["quantum_usado"] >= _QUANTUM_DEFECTO
                and clave_candidato <= clave_actual
            ):
                _cpus[cpu_idx] = None
                _cambiar_estado(pcb_actual, "LISTO")

    _ordenar_cola_listos()
    for cpu_idx in range(len(_cpus)):
        if _cpus[cpu_idx] is None and _cola_listos:
            siguiente_pid = _cola_listos.pop(0)
            pcb = _procesos[siguiente_pid]
            _cpus[cpu_idx] = siguiente_pid
            _cambiar_estado(pcb, "EJECUTANDO")
            _cambios_contexto += 1
            if pcb["primera_ejecucion"] is None:
                pcb["primera_ejecucion"] = reloj


def ejecutar_instrucciones_cpus(reloj: int) -> None:
    """Ejecuta 1 tick en cada CPU asignada avanzando el hilo activo del proceso."""
    global _ticks_cpu_ocupados, _reloj_ref
    _reloj_ref = reloj

    for cpu_idx in range(len(_cpus)):
        pid = _cpus[cpu_idx]
        if pid is None:
            continue

        pcb = _procesos[pid]
        hilo = _seleccionar_hilo_ejecutable(pcb)
        if hilo is None:
            terminar_proceso(pid)
            continue

        _ticks_cpu_ocupados += 1
        pcb["cpu_usada"] += 1
        pcb["quantum_usado"] += 1

        op, arg = hilo["programa"][hilo["ip"]]
        if op == "CPU":
            if hilo["inst_restante"] <= 0:
                hilo["inst_restante"] = int(arg)
            hilo["inst_restante"] -= 1
            if hilo["inst_restante"] <= 0:
                hilo["ip"] += 1
                _avanzar_instrucciones_hilo(pcb, hilo)
        else:
            _avanzar_instrucciones_hilo(pcb, hilo)


def aplicar_vigilancia() -> None:
    """Actualiza espera en cola y aplica envejecimiento contra inanición."""
    for pid in list(_cola_listos):
        pcb = _procesos[pid]
        pcb["tiempo_espera"] += 1
        pcb["espera_consecutiva"] += 1
        if pcb["espera_consecutiva"] > pcb["max_espera_consecutiva"]:
            pcb["max_espera_consecutiva"] = pcb["espera_consecutiva"]
        pcb["bono_envejecimiento"] = pcb["espera_consecutiva"] // _INTERVALO_ENVEJECIMIENTO

    _ordenar_cola_listos()


def ejecutar_ciclo_cpus(reloj: int) -> None:
    """Agrupa planificación, ejecución y vigilancia."""
    planificar_cpus(reloj)
    ejecutar_instrucciones_cpus(reloj)
    aplicar_vigilancia()


def estado_proceso(pid: int) -> str:
    """Devuelve el estado actual del proceso."""
    return _obtener_pcb(pid)["estado"]


def listar_procesos() -> list[dict]:
    """Devuelve una lista de copias con la información resumida de cada proceso."""
    resultado = []
    for pid in sorted(_procesos.keys()):
        pcb = _procesos[pid]
        resultado.append(
            {
                "pid": pcb["pid"],
                "nombre": pcb["nombre"],
                "usuario": pcb["usuario"],
                "estado": pcb["estado"],
                "prioridad": pcb["prioridad"],
                "cpu_usada": pcb["cpu_usada"],
                "tiempo_espera": pcb["tiempo_espera"],
            }
        )
    return resultado


def cola_listos() -> list[int]:
    """Devuelve una copia ordenada de los PID en cola de listos."""
    _ordenar_cola_listos()
    return list(_cola_listos)


def proceso_en_ejecucion(cpu: int = 0) -> Optional[int]:
    """Devuelve el PID en ejecución en la CPU indicada, o None si está libre."""
    if cpu < 0 or cpu >= len(_cpus):
        raise ErrorSistema(f"Índice de CPU inválido: {cpu}")
    return _cpus[cpu]


def politica_planificacion() -> str:
    """Nombre descriptivo de la política de planificación implementada."""
    return "Triage Apropiativo con Quantum (Q=3) y Envejecimiento"


def metricas_planificacion() -> dict:
    """Calcula los indicadores de atención y utilización del sistema."""
    total_procesos = len(_procesos)
    if total_procesos == 0:
        return {
            "espera_promedio": 0.0,
            "respuesta_promedio": 0.0,
            "retorno_promedio": 0.0,
            "espera_maxima": 0,
            "utilizacion_cpu": 0.0,
            "cambios_contexto": _cambios_contexto,
            "procesos_terminados": 0,
        }

    esperas = [p["tiempo_espera"] for p in _procesos.values()]
    espera_promedio = sum(esperas) / total_procesos
    espera_maxima = max(
        (p["max_espera_consecutiva"] for p in _procesos.values()),
        default=0,
    )

    respuestas = [
        p["primera_ejecucion"] - p["tick_llegada"]
        for p in _procesos.values()
        if p["primera_ejecucion"] is not None
    ]
    respuesta_promedio = sum(respuestas) / len(respuestas) if respuestas else 0.0

    terminados = [p for p in _procesos.values() if p["estado"] == "TERMINADO"]
    retornos = [
        p["tick_fin"] - p["tick_llegada"]
        for p in terminados
        if p["tick_fin"] is not None
    ]
    retorno_promedio = sum(retornos) / len(retornos) if retornos else 0.0

    capacidad_cpu = max(1, _reloj_ref * len(_cpus))
    utilizacion_cpu = min(1.0, _ticks_cpu_ocupados / capacidad_cpu) if _reloj_ref > 0 else 0.0

    return {
        "espera_promedio": round(espera_promedio, 4),
        "respuesta_promedio": round(respuesta_promedio, 4),
        "retorno_promedio": round(retorno_promedio, 4),
        "espera_maxima": espera_maxima,
        "utilizacion_cpu": round(utilizacion_cpu, 4),
        "cambios_contexto": _cambios_contexto,
        "procesos_terminados": len(terminados),
    }


def _contar_activos() -> int:
    """Cantidad de procesos activos en el sistema."""
    return sum(1 for p in _procesos.values() if p["estado"] != "TERMINADO")