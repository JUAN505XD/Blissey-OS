"""Pruebas unitarias y de requisitos medibles (RP1, RP2, RP3) para Prototipo 1."""

import json

from minidc import archivos, consola, disco, kernel, memoria, procesos, sincronizacion


def test_importaciones_y_ciclo_basico():
    kernel.iniciar_sistema({"num_cpus": 1})
    assert kernel.reloj_actual() == 0

    pid = procesos.crear_proceso(
        nombre="web",
        usuario="cliente_a",
        programa=[["CPU", 2], ["ES", 10], ["CPU", 1]],
        prioridad=1,
    )
    assert procesos.estado_proceso(pid) == "LISTO"

    kernel.ejecutar_ticks(10)
    assert procesos.estado_proceso(pid) == "TERMINADO"
    resumen = kernel.apagar_sistema()
    assert resumen["procesos_activos"] == 0


def test_rp1_respuesta_servicios_web_menor_igual_10_ticks(tmp_path):
    """RP1: Servicios web empiezan a ejecutarse en promedio dentro de 10 ticks."""
    escenario = {
        "config": {"num_cpus": 1, "marcos_fisicos": 16, "tam_pagina": 256,
                   "bloques_disco": 200, "tam_bloque": 512, "cache_bloques": 8},
        "usuarios": ["cliente_a", "cliente_b"],
        "semaforos": {"bd": 1},
        "catalogo": {
            "analitica": {
                "memoria_bytes": 4096,
                "cuota_marcos": 6,
                "prioridad": 0,
                "programa": [["CPU", 40]],
            },
            "web": {
                "memoria_bytes": 1024,
                "cuota_marcos": 3,
                "prioridad": 2,
                "programa": [["CPU", 2], ["ES", 10], ["CPU", 1]],
            },
        },
        "llegadas": [
            {"tick": 0, "programa": "analitica", "usuario": "cliente_b"},
            {"tick": 3, "programa": "web", "usuario": "cliente_a"},
            {"tick": 8, "programa": "web", "usuario": "cliente_a"},
            {"tick": 14, "programa": "web", "usuario": "cliente_a"},
        ],
    }
    ruta = tmp_path / "escenario_base.json"
    ruta.write_text(json.dumps(escenario), encoding="utf-8")

    kernel.cargar_escenario(str(ruta))
    kernel.ejecutar_ticks(60)

    metricas = procesos.metricas_planificacion()
    assert metricas["respuesta_promedio"] <= 10.0


def test_rp2_sin_inanicion_menor_150_ticks():
    """RP2: Ningún proceso espera más de 150 ticks consecutivos en cola de listos."""
    kernel.iniciar_sistema({"num_cpus": 1})

    # Proceso de baja prioridad llega primero y compite contra ráfagas continuas de alta prioridad
    pid_lento = procesos.crear_proceso(
        nombre="analitica_pesada",
        usuario="cliente_b",
        programa=[["CPU", 5]],
        prioridad=0,
    )

    for tick_actual in range(220):
        if tick_actual % 2 == 0:
            procesos.crear_proceso(
                nombre="web_rafaga",
                usuario="cliente_a",
                programa=[["CPU", 2]],
                prioridad=3,
            )
        kernel.tick()

    metricas = procesos.metricas_planificacion()
    assert metricas["espera_maxima"] < 150
    assert procesos.estado_proceso(pid_lento) == "TERMINADO"


def test_rp3_utilizacion_cpu_mayor_igual_85_por_ciento():
    """RP3: Con carga suficiente, la utilización de CPU es de al menos 85%."""
    kernel.iniciar_sistema({"num_cpus": 2})

    for i in range(6):
        procesos.crear_proceso(
            nombre=f"batch_{i}",
            usuario="cliente_a",
            programa=[["CPU", 30]],
            prioridad=1,
        )

    kernel.ejecutar_ticks(80)
    metricas = procesos.metricas_planificacion()
    assert metricas["utilizacion_cpu"] >= 0.85


def test_consola_comandos_prototipo1(tmp_path):
    """Verifica ps, run, kill, tick, top y formato de errores en consola."""
    escenario = {
        "config": {"num_cpus": 1},
        "usuarios": ["cliente_a"],
        "catalogo": {
            "web": {"memoria_bytes": 1024, "cuota_marcos": 2, "prioridad": 1, "programa": [["CPU", 10]]}
        },
        "llegadas": [],
    }
    ruta = tmp_path / "escenario_consola.json"
    ruta.write_text(json.dumps(escenario), encoding="utf-8")
    kernel.cargar_escenario(str(ruta))

    salida_run = consola.ejecutar_comando("run web", usuario="cliente_a")
    assert "PID 1" in salida_run

    salida_ps = consola.ejecutar_comando("ps")
    assert salida_ps.startswith("PID NOMBRE USUARIO ESTADO")
    assert "1 web cliente_a LISTO" in salida_ps

    salida_tick = consola.ejecutar_comando("tick 3")
    assert "tick 3" in salida_tick

    salida_top = consola.ejecutar_comando("top")
    assert "Utilización CPU:" in salida_top

    salida_kill = consola.ejecutar_comando("kill 1")
    assert "terminado" in salida_kill
    assert procesos.estado_proceso(1) == "TERMINADO"

    salida_error = consola.ejecutar_comando("kill 999")
    assert salida_error.startswith("Error:")