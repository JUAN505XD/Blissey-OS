"""Demostración visual e interactiva en consola para Blissey OS (Prototipo 1)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from minidc import consola, kernel, procesos

os.system("")

VERDE = "\033[92m"
AMARILLO = "\033[93m"
ROJO = "\033[91m"
CIAN = "\033[96m"
NEGRITA = "\033[1m"
GRIS = "\033[90m"
RESET = "\033[0m"

ESCENARIO_HOSPITAL = {
    "config": {
        "num_cpus": 1,
        "marcos_fisicos": 16,
        "tam_pagina": 256,
        "bloques_disco": 200,
        "tam_bloque": 512,
        "cache_bloques": 8,
    },
    "usuarios": ["medico_a", "enfermeria_b"],
    "semaforos": {"historia_clinica": 1},
    "catalogo": {
        "observacion_larga": {
            "memoria_bytes": 4096,
            "cuota_marcos": 6,
            "prioridad": 0,
            "programa": [["CPU", 25]],
        },
        "triage_rojo": {
            "memoria_bytes": 1024,
            "cuota_marcos": 3,
            "prioridad": 3,
            "programa": [["CPU", 3], ["ES", 10], ["CPU", 2]],
        },
        "web": {
            "memoria_bytes": 1024,
            "cuota_marcos": 3,
            "prioridad": 2,
            "programa": [["CPU", 2], ["ES", 20], ["CPU", 1]],
        },
    },
    "llegadas": [
        {"tick": 0, "programa": "observacion_larga", "usuario": "enfermeria_b"},
        {"tick": 3, "programa": "triage_rojo", "usuario": "medico_a"},
        {"tick": 6, "programa": "web", "usuario": "medico_a"},
        {"tick": 12, "programa": "web", "usuario": "medico_a"},
    ],
}


def banner(titulo: str) -> None:
    ancho = 82
    print(f"\n{CIAN}{NEGRITA}{'=' * ancho}")
    print(f"  {titulo}")
    print(f"{'=' * ancho}{RESET}")


def barra_progreso(porcentaje: float, largo: int = 30) -> str:
    llenos = int(round(min(1.0, max(0.0, porcentaje)) * largo))
    vacios = largo - llenos
    color = VERDE if porcentaje >= 0.85 else AMARILLO
    return f"{color}[{'#' * llenos}{'-' * vacios}] {porcentaje * 100:6.2f}%{RESET}"


def cargar_escenario_demo() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ruta_json = Path(tmpdir) / "hospital_base.json"
        ruta_json.write_text(json.dumps(ESCENARIO_HOSPITAL), encoding="utf-8")
        kernel.cargar_escenario(str(ruta_json))


def demo_rp1_traza_gantt() -> dict:
    banner("1. TRAZA EN VIVO Y DIAGRAMA DE GANTT (RP1: Respuesta <= 10 ticks)")
    cargar_escenario_demo()
    print(f"{GRIS}Política activa: {procesos.politica_planificacion()}{RESET}\n")

    pid_anterior = None
    for t in range(1, 22):
        kernel.tick()
        pid_cpu = procesos.proceso_en_ejecucion(0)
        listos = procesos.cola_listos()

        if pid_cpu is not None:
            pcb = procesos._procesos[pid_cpu]
            nombre = pcb["nombre"]
            prio = pcb["prioridad"]
            evento = ""

            if pid_anterior is not None and pid_anterior != pid_cpu and prio >= 2:
                latencia = pcb["primera_ejecucion"] - pcb["tick_llegada"]
                evento = f" {AMARILLO}<- ¡APROPIACIÓN! Inicio en {latencia} ticks{RESET}"
            elif pcb["primera_ejecucion"] == t:
                latencia = pcb["primera_ejecucion"] - pcb["tick_llegada"]
                evento = f" {VERDE}<- Primera ejecución (latencia: {latencia} ticks){RESET}"

            color_proc = ROJO if prio >= 3 else (CIAN if prio == 2 else GRIS)
            bloque_cpu = f"{color_proc}[PID {pid_cpu}: {nombre:<17} P={prio}]{RESET}"
        else:
            bloque_cpu = f"{GRIS}[CPU INACTIVA                 ]{RESET}"
            evento = ""

        pid_anterior = pid_cpu
        cola_txt = f"Listos: {listos}" if listos else "Listos: []"
        print(f"Tick {t:02d} | CPU0: {bloque_cpu} | {cola_txt:<18}{evento}")

    kernel.ejecutar_ticks(25)
    met = procesos.metricas_planificacion()
    print(
        f"\n{NEGRITA}Métrica RP1 -> Respuesta promedio: {VERDE}{met['respuesta_promedio']:.2f} ticks{RESET} "
        f"(Exigido: <= 10.00 ticks)"
    )
    return met


def demo_rp2_envejecimiento() -> dict:
    banner("2. SIMULACIÓN DE ESTRÉS Y ENVEJECIMIENTO (RP2: Sin inanición < 150 ticks)")
    kernel.iniciar_sistema({"num_cpus": 1})

    pid_lento = procesos.crear_proceso(
        nombre="consulta_general",
        usuario="enfermeria_b",
        programa=[["CPU", 4]],
        prioridad=0,
    )
    print(f"Tick 000 | Ingresa {AMARILLO}PID {pid_lento} (consulta_general, prioridad base=0){RESET}")
    print(f"{GRIS}Inyectando ráfagas continuas de triage_rojo (prioridad=3) cada 2 ticks...{RESET}\n")

    rescatado = False
    for t in range(1, 120):
        if t % 2 == 1:
            procesos.crear_proceso(
                nombre="triage_rojo",
                usuario="medico_a",
                programa=[["CPU", 2]],
                prioridad=3,
            )
        kernel.tick()

        pcb_lento = procesos._procesos[pid_lento]
        if not rescatado:
            if pcb_lento["estado"] == "EJECUTANDO":
                print(
                    f"{VERDE}{NEGRITA}Tick {t:03d} | ¡RESCATADO! consulta_general entra a CPU "
                    f"(espera máxima consecutiva: {pcb_lento['max_espera_consecutiva']} ticks < 150){RESET}"
                )
                rescatado = True
            elif t % 10 == 0:
                eff = pcb_lento["prioridad"] + pcb_lento["bono_envejecimiento"]
                print(
                    f"Tick {t:03d} | En espera: {pcb_lento['espera_consecutiva']:02d} ticks | "
                    f"Prioridad: base 0 + bono +{pcb_lento['bono_envejecimiento']} = {CIAN}Efectiva {eff}{RESET}"
                )

    met = procesos.metricas_planificacion()
    print(
        f"\n{NEGRITA}Métrica RP2 -> Espera máxima consecutiva: {VERDE}{met['espera_maxima']} ticks{RESET} "
        f"(Exigido: < 150 ticks)"
    )
    return met


def demo_rp3_utilizacion_cpu() -> dict:
    banner("3. CARGA PARALELA MULTI-CPU (RP3: Utilización de CPU >= 85%)")
    kernel.iniciar_sistema({"num_cpus": 2})

    for i in range(1, 7):
        procesos.crear_proceso(
            nombre=f"cirugia_urg_{i}",
            usuario="medico_a",
            programa=[["CPU", 25]],
            prioridad=1,
        )

    kernel.ejecutar_ticks(60)
    met = procesos.metricas_planificacion()

    print(f"CPUs activas: 2 | Ticks simulados: 60 | Procesos atendidos: {met['procesos_terminados']}/6")
    print(f"Utilización obtenida : {barra_progreso(met['utilizacion_cpu'])}")
    print(f"Umbral mínimo rúbrica: {barra_progreso(0.85)}")
    print(f"Cambios de contexto  : {met['cambios_contexto']}")
    return met


def tabla_resumen_rubrica(met_rp1: dict, met_rp2: dict, met_rp3: dict) -> None:
    banner("4. VERIFICACIÓN FINAL DE RÚBRICA - PROTOTIPO 1 (BLISSEY OS)")
    criterios = [
        ("RP1", "Inicio promedio urgencias/web <= 10 ticks", f"{met_rp1['respuesta_promedio']:.2f} ticks", met_rp1["respuesta_promedio"] <= 10.0),
        ("RP2", "Espera máxima consecutiva < 150 ticks", f"{met_rp2['espera_maxima']} ticks", met_rp2["espera_maxima"] < 150),
        ("RP3", "Utilización de CPU >= 85.0%", f"{met_rp3['utilizacion_cpu'] * 100:.2f}%", met_rp3["utilizacion_cpu"] >= 0.85),
    ]

    print(f"{NEGRITA}{'COD':<6} | {'REQUISITO MEDIBLE':<43} | {'VALOR':<13} | {'ESTADO'}{RESET}")
    print("-" * 82)
    for cod, desc, valor, ok in criterios:
        estado = f"{VERDE}{NEGRITA}CUMPLE{RESET}" if ok else f"{ROJO}{NEGRITA}NO CUMPLE{RESET}"
        print(f"{cod:<6} | {desc:<43} | {valor:<13} | {estado}")


def consola_interactiva() -> None:
    cargar_escenario_demo()
    banner("CONSOLA DE ADMINISTRACIÓN BLISSEY OS (escribe 'salir' para terminar)")
    print(f"{GRIS}Catálogo activo: observacion_larga, triage_rojo, web{RESET}")
    print(f"{CIAN}Comandos: ps | top | admitir <nombre> | run <nombre> | tick [N] | kill <PID> | free | df | pwd | whoami{RESET}\n")

    while True:
        try:
            cmd = input(f"{VERDE}BlisseyOS [admin]>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo de Blissey OS.")
            break

        if cmd.lower() in ("salir", "exit", "quit"):
            print("Sesión finalizada.")
            break
        if not cmd:
            continue

        salida = consola.ejecutar_comando(cmd, usuario="admin")
        if salida.startswith("Error:"):
            print(f"{ROJO}{salida}{RESET}")
        elif salida:
            print(salida)


if __name__ == "__main__":
    r1 = demo_rp1_traza_gantt()
    r2 = demo_rp2_envejecimiento()
    r3 = demo_rp3_utilizacion_cpu()
    tabla_resumen_rubrica(r1, r2, r3)
    consola_interactiva()