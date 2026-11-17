"""Gestión de procesos (pacientes/atenciones), hilos y planificación por urgencia de Blissey OS."""

from __future__ import annotations

from typing import Optional

from .errores import ErrorNoExiste, ErrorSistema

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
    """Convierte las instrucciones del protocolo de atención a tuplas normalizadas."""
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


def _clave_planificacion(pid: int) -> tuple:
    """Calcula la prioridad efectiva considerando nivel de urgencia (triage) y envejecimiento."""
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
    """Ordena la sala de espera (cola de listos) según urgencia efectiva."""
    _cola_listos.sort(key=_clave_planificacion)


def _obtener_pcb(pid: int) -> dict:
    if pid not in _procesos:
        raise ErrorNoExiste(f"El proceso/paciente con PID {pid} no existe.")
    return _procesos[pid]


def _cambiar_estado(pcb: dict, nuevo_estado: str) -> None:
    """Centraliza las transiciones de estado del proceso (regla de aislamiento Blissey OS)."""
    if nuevo_estado not in ESTADOS_VALIDOS:
        raise ErrorSistema(f"Estado de proceso inválido: {nuevo_estado}")
    estado_anterior = pcb["estado"]
    if estado_anterior == nuevo_estado:
        return
    if estado_anterior == "TERMINADO":
        raise ErrorSistema(
            f"El proceso PID {pcb['pid']} ya está TERMINADO y no puede cambiar de estado."
        )

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
    """Registra un nuevo proceso/paciente en el sistema y lo ingresa a la cola LISTO."""
    global _siguiente_pid, _siguiente_tid

    pid = _siguiente_pid
    _siguiente_pid += 1

    tid_principal = _siguiente_tid
    _siguiente_tid += 1

    prog_norm = _normalizar_programa(programa)
    inst_restante = prog_norm[0][1] if prog_norm and prog_norm[0][0] == "CPU" else 0

    pcb = {
        "pid": pid,
        "nombre": str(nombre),
        "usuario": str(usuario),
        "programa": prog_norm,
        "ip": 0,
        "inst_restante": inst_restante,
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
        "hilos": [{"tid": tid_principal, "estado": "LISTO"}],
    }
    _procesos[pid] = pcb
    _cambiar_estado(pcb, "LISTO")
    return pid


def crear_hilo(pid: int, programa: list) -> int:
    """Crea un hilo de actividad clínica asociado a un proceso existente."""
    global _siguiente_tid
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        raise ErrorSistema(f"No se pueden crear hilos en el proceso terminado {pid}.")

    tid = _siguiente_tid
    _siguiente_tid += 1
    prog_hilo = _normalizar_programa(programa)
    pcb["hilos"].append({"tid": tid, "programa": prog_hilo, "estado": "LISTO"})
    pcb["programa"].extend(prog_hilo)
    if pcb["ip"] < len(pcb["programa"]) and pcb["inst_restante"] == 0:
        if pcb["programa"][pcb["ip"]][0] == "CPU":
            pcb["inst_restante"] = pcb["programa"][pcb["ip"]][1]
    return tid


def _liberar_recursos_proceso(pid: int) -> None:
    """Libera memoria y semáforos/mutex asignados al proceso al finalizar."""
    from . import memoria, sincronizacion

    memoria.liberar_memoria(pid)
    sincronizacion._liberar_recursos_pid(pid)


def terminar_proceso(pid: int) -> None:
    """Finaliza un proceso (alta médica o cancelación) y libera sus recursos."""
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        return

    for idx, cpu_pid in enumerate(_cpus):
        if cpu_pid == pid:
            _cpus[idx] = None

    _cambiar_estado(pcb, "TERMINADO")
    pcb["tick_fin"] = _reloj_ref
    pcb["bloqueo_restante"] = 0
    pcb["motivo_bloqueo"] = None
    for hilo in pcb["hilos"]:
        hilo["estado"] = "TERMINADO"

    _liberar_recursos_proceso(pid)


def bloquear_proceso(pid: int, ticks_bloqueo: int, motivo: str = "ES") -> None:
    """Pasa un proceso a estado BLOQUEADO por exámenes de E/S o fallo de página."""
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "TERMINADO":
        return

    for idx, cpu_pid in enumerate(_cpus):
        if cpu_pid == pid:
            _cpus[idx] = None

    pcb["bloqueo_restante"] = max(1, int(ticks_bloqueo))
    pcb["motivo_bloqueo"] = motivo
    _cambiar_estado(pcb, "BLOQUEADO")


def despertar_proceso(pid: int) -> None:
    """Reincorpora un proceso BLOQUEADO a la cola de LISTO."""
    pcb = _obtener_pcb(pid)
    if pcb["estado"] == "BLOQUEADO":
        pcb["bloqueo_restante"] = 0
        pcb["motivo_bloqueo"] = None
        _cambiar_estado(pcb, "LISTO")


def procesar_interrupciones_bloqueo() -> None:
    """Paso 3 del ciclo: descuenta tiempos de bloqueo y despierta procesos listos."""
    for pcb in list(_procesos.values()):
        if pcb["estado"] == "BLOQUEADO" and pcb["bloqueo_restante"] > 0:
            pcb["bloqueo_restante"] -= 1
            if pcb["bloqueo_restante"] == 0:
                despertar_proceso(pcb["pid"])


def _preparar_siguiente_instruccion(pcb: dict, reloj: int) -> None:
    """Prepara la siguiente instrucción del proceso o inicia bloqueo por E/S o memoria."""
    from . import disco, memoria

    while pcb["estado"] != "TERMINADO" and pcb["ip"] < len(pcb["programa"]):
        op, arg = pcb["programa"][pcb["ip"]]
        if op == "CPU":
            if pcb["inst_restante"] <= 0:
                pcb["inst_restante"] = int(arg)
            if pcb["inst_restante"] > 0:
                return
            pcb["ip"] += 1
        elif op == "ES":
            pcb["ip"] += 1
            ticks_es = disco._registrar_es_kernel(pcb["pid"], int(arg))
            bloquear_proceso(pcb["pid"], ticks_es, motivo="ES")
            return
        elif op == "MEM":
            pcb["ip"] += 1
            res = memoria.acceder_memoria(pcb["pid"], int(arg))
            if res.get("fallo_pagina", False):
                bloquear_proceso(pcb["pid"], 5, motivo="MEM")
                return
        elif op in ("WAIT", "SIGNAL"):
            pcb["ip"] += 1
        else:
            pcb["ip"] += 1

    if pcb["ip"] >= len(pcb["programa"]) and pcb["estado"] != "TERMINADO":
        terminar_proceso(pcb["pid"])


def planificar_cpus(reloj: int) -> None:
    """Paso 4 del ciclo: evalúa apropiación por urgencia/quantum y asigna CPUs libres."""
    global _cambios_contexto, _reloj_ref
    _reloj_ref = reloj

    _ordenar_cola_listos()
    candidatos_evaluados = 0

    # Evaluar apropiación en CPUs activas sin desalojar más CPUs que candidatos disponibles
    for cpu_idx in range(len(_cpus)):
        pid_actual = _cpus[cpu_idx]
        if pid_actual is None:
            continue

        pcb_actual = _procesos.get(pid_actual)
        if pcb_actual is None or pcb_actual["estado"] != "EJECUTANDO":
            _cpus[cpu_idx] = None
            continue

        if candidatos_evaluados < len(_cola_listos):
            mejor_candidato = _cola_listos[candidatos_evaluados]
            clave_candidato = _clave_planificacion(mejor_candidato)
            clave_actual = _clave_planificacion(pid_actual)

            if clave_candidato[:2] < clave_actual[:2] or (
                pcb_actual["quantum_usado"] >= _QUANTUM_DEFECTO
                and clave_candidato <= clave_actual
            ):
                _cpus[cpu_idx] = None
                _cambiar_estado(pcb_actual, "LISTO")
                candidatos_evaluados += 1

    # Despachar procesos a CPUs disponibles
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
    """Paso 5 del ciclo: ejecuta 1 tick de CPU en cada unidad asignada."""
    global _ticks_cpu_ocupados, _reloj_ref
    _reloj_ref = reloj

    for cpu_idx in range(len(_cpus)):
        pid = _cpus[cpu_idx]
        if pid is None:
            continue

        pcb = _procesos[pid]
        _ticks_cpu_ocupados += 1
        pcb["cpu_usada"] += 1
        pcb["quantum_usado"] += 1

        if pcb["ip"] >= len(pcb["programa"]):
            terminar_proceso(pid)
            continue

        op, arg = pcb["programa"][pcb["ip"]]
        if op == "CPU":
            if pcb["inst_restante"] <= 0:
                pcb["inst_restante"] = int(arg)
            pcb["inst_restante"] -= 1
            if pcb["inst_restante"] <= 0:
                pcb["ip"] += 1
                _preparar_siguiente_instruccion(pcb, reloj)
        else:
            _preparar_siguiente_instruccion(pcb, reloj)


def aplicar_vigilancia() -> None:
    """Paso 6 del ciclo: actualiza espera en sala y aplica envejecimiento contra inanición."""
    for pid in list(_cola_listos):
        pcb = _procesos[pid]
        pcb["tiempo_espera"] += 1
        pcb["espera_consecutiva"] += 1
        if pcb["espera_consecutiva"] > pcb["max_espera_consecutiva"]:
            pcb["max_espera_consecutiva"] = pcb["espera_consecutiva"]
        pcb["bono_envejecimiento"] = pcb["espera_consecutiva"] // _INTERVALO_ENVEJECIMIENTO

    _ordenar_cola_listos()


def ejecutar_ciclo_cpus(reloj: int) -> None:
    """Método de compatibilidad que agrupa planificación, ejecución y vigilancia."""
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
    """Nombre descriptivo de la política de planificación hospitalaria implementada."""
    return "Triage Apropiativo con Quantum (Q=3) y Envejecimiento"


def metricas_planificacion() -> dict:
    """Paso 7 del ciclo: calcula los indicadores de atención y utilización del sistema."""
    total_procesos = len(_procesos)
    if total_procesos == 0:
        return {
            "espera_promedio": 0.0,
            "respuesta_promedio": 0.0,
            "respuesta_promedio_web": 0.0,
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
        (p["primera_ejecucion"] if p["primera_ejecucion"] is not None else _reloj_ref)
        - p["tick_llegada"]
        for p in _procesos.values()
    ]
    respuesta_promedio = sum(respuestas) / len(respuestas) if respuestas else 0.0

    # Métrica específica RP1: servicios web
    respuestas_web = [
        (p["primera_ejecucion"] if p["primera_ejecucion"] is not None else _reloj_ref)
        - p["tick_llegada"]
        for p in _procesos.values()
        if "web" in p["nombre"].lower()
    ]
    respuesta_promedio_web = (
        sum(respuestas_web) / len(respuestas_web)
        if respuestas_web
        else respuesta_promedio
    )

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
        "respuesta_promedio_web": round(respuesta_promedio_web, 4),
        "retorno_promedio": round(retorno_promedio, 4),
        "espera_maxima": espera_maxima,
        "utilizacion_cpu": round(utilizacion_cpu, 4),
        "cambios_contexto": _cambios_contexto,
        "procesos_terminados": len(terminados),
    }


def _contar_activos() -> int:
    """Cantidad de procesos/pacientes activos en el hospital."""
    return sum(1 for p in _procesos.values() if p["estado"] != "TERMINADO")