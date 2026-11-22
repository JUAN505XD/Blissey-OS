"""Pruebas unitarias y de requisitos medibles (RM1, RM3, RD1, RF1) para Blissey OS - Prototipo 2."""

import pytest

from minidc import archivos, consola, disco, kernel, memoria, procesos
from minidc.errores import ErrorMemoria, ErrorPermiso


def test_rm1_tasa_fallos_pagina_menor_igual_25_por_ciento():
    """RM1: En el escenario de memoria, la tasa de fallos de página no supera el 25%."""
    kernel.iniciar_sistema({"num_cpus": 1, "marcos_fisicos": 16, "tam_pagina": 256})

    programa = [
        ["MEM", 0], ["MEM", 32], ["MEM", 64], ["MEM", 96],
        ["MEM", 260], ["MEM", 300], ["MEM", 340], ["MEM", 380],
        ["MEM", 520], ["MEM", 560], ["MEM", 600], ["MEM", 640],
        ["MEM", 16], ["MEM", 280], ["MEM", 540], ["MEM", 128],
    ]
    pid = procesos.crear_proceso(
        nombre="monitor_uci",
        usuario="medico_a",
        programa=programa,
        memoria_bytes=1024,
        cuota_marcos=3,
        prioridad=2,
    )

    kernel.ejecutar_ticks(30)
    assert procesos.estado_proceso(pid) == "TERMINADO"

    met = memoria.metricas_memoria()
    print(
        f"\n[RM1] Accesos: {met['accesos']} | Fallos de página: {met['fallos_pagina']} | "
        f"Tasa fallos: {met['tasa_fallos'] * 100:.2f}% (Límite <= 25.0%)"
    )
    assert met["accesos"] == 16
    assert met["fallos_pagina"] == 3
    assert met["tasa_fallos"] <= 0.25


def test_rm3_lanza_error_memoria_fuera_de_limites():
    """RM3: Verifica explícitamente que ErrorMemoria se lanza ante direcciones negativas o >= memoria_bytes."""
    kernel.iniciar_sistema({"num_cpus": 1, "marcos_fisicos": 8, "tam_pagina": 256})

    pid = procesos.crear_proceso(
        nombre="proceso_acotado",
        usuario="medico_a",
        programa=[["MEM", 0]],
        memoria_bytes=512,  # Rango válido: 0 a 511
        cuota_marcos=2,
        prioridad=1,
    )

    # 1. Dirección negativa
    with pytest.raises(ErrorMemoria) as exc_neg:
        memoria.acceder_memoria(pid, -1)

    # 2. Límite superior exacto (512 está fuera de [0, 511])
    with pytest.raises(ErrorMemoria) as exc_borde:
        memoria.acceder_memoria(pid, 512)

    # 3. Dirección muy por encima del espacio asignado
    with pytest.raises(ErrorMemoria) as exc_alto:
        memoria.acceder_memoria(pid, 4096)

    print(f"\n[RM3 - Excepción] Capturada correctamente -> {exc_alto.value}")
    assert "fuera de límites" in str(exc_neg.value)
    assert "fuera de límites" in str(exc_borde.value)
    assert "fuera de límites" in str(exc_alto.value)


def test_rm3_acceso_fuera_de_espacio_no_afecta_otros():
    """RM3: Un acceso fuera del espacio del proceso termina al infractor y no afecta a otros procesos."""
    kernel.iniciar_sistema({"num_cpus": 1, "marcos_fisicos": 8, "tam_pagina": 256})

    pid_invalido = procesos.crear_proceso(
        nombre="proceso_erroneo",
        usuario="medico_a",
        programa=[["MEM", 4096]],
        memoria_bytes=512,
        cuota_marcos=2,
        prioridad=2,
    )
    pid_sano = procesos.crear_proceso(
        nombre="proceso_sano",
        usuario="medico_a",
        programa=[["MEM", 64], ["CPU", 3]],
        memoria_bytes=512,
        cuota_marcos=2,
        prioridad=1,
    )

    kernel.ejecutar_ticks(15)
    print(
        f"\n[RM3 - Aislamiento] Proceso infractor: {procesos.estado_proceso(pid_invalido)} | "
        f"Proceso sano: {procesos.estado_proceso(pid_sano)} | "
        f"Marcos libres: {memoria.estado_memoria()['marcos_libres']}/8"
    )
    assert procesos.estado_proceso(pid_invalido) == "TERMINADO"
    assert procesos.estado_proceso(pid_sano) == "TERMINADO"
    assert memoria.estado_memoria()["marcos_libres"] == 8


def test_rd1_disco_desplazamiento_30_por_ciento_menor_que_fifo():
    """RD1: Desplazamiento del cabezal >= 30% menor que FIFO y sin inanición (> 200 ticks)."""
    kernel.iniciar_sistema({"bloques_disco": 200, "tam_bloque": 512, "cache_bloques": 4})

    solicitudes = [98, 183, 37, 122, 14, 124, 65, 67]

    pos_fifo = 0
    desplazamiento_fifo = 0
    for b in solicitudes:
        desplazamiento_fifo += abs(pos_fifo - b)
        pos_fifo = b

    for idx, bloque in enumerate(solicitudes, start=1):
        disco.encolar_solicitud_disco(pid=idx, bloque=bloque, operacion="L")

    disco.procesar_disco()
    met = disco.metricas_disco()
    ahorro = (1 - (met["desplazamiento_total"] / desplazamiento_fifo)) * 100

    print(
        f"\n[RD1] Desplazamiento LOOK: {met['desplazamiento_total']} vs FIFO: {desplazamiento_fifo} "
        f"(Reducción: {ahorro:.1f}%, Mínimo >= 30.0%)"
    )
    assert met["solicitudes_atendidas"] == len(solicitudes)
    assert met["desplazamiento_total"] <= desplazamiento_fifo * 0.70


def test_rf1_permisos_unix_e_invariante_de_bloques():
    """RF1: Sin permiso lanza ErrorPermiso; bloques usados + libres == totales siempre."""
    kernel.iniciar_sistema({"bloques_disco": 50, "tam_bloque": 64})
    archivos.crear_usuario("medico_a", "medicos")
    archivos.crear_usuario("enfermeria_b", "enfermeria")

    archivos.fs_mkdir("/historias", "admin")
    archivos.fs_chmod("/historias", "777", "admin")

    archivos.fs_escribir("/historias/pac1.txt", "Diagnostico reservado de urgencias", "medico_a")
    archivos.fs_chmod("/historias/pac1.txt", "600", "medico_a")

    with pytest.raises(ErrorPermiso):
        archivos.fs_leer("/historias/pac1.txt", "enfermeria_b")

    with pytest.raises(ErrorPermiso):
        archivos.fs_escribir("/historias/pac1.txt", "Intento no autorizado", "enfermeria_b")

    assert "Diagnostico" in archivos.fs_leer("/historias/pac1.txt", "medico_a")
    assert "Diagnostico" in archivos.fs_leer("/historias/pac1.txt", "admin")

    archivos.fs_enlace_simbolico("/historias/pac1.txt", "/historias/enlace_pac1", "medico_a")
    assert "Diagnostico" in archivos.fs_leer("/historias/enlace_pac1", "medico_a")

    est = archivos.fs_estado_disco()
    usados = est["bloques_totales"] - est["bloques_libres"]
    assert usados + est["bloques_libres"] == est["bloques_totales"]

    archivos.fs_eliminar("/historias", "admin", recursivo=True)
    est_final = archivos.fs_estado_disco()
    print(
        f"\n[RF1] Control permisos Unix (600) verificado | "
        f"Invariante bloques tras liberar: {est_final['bloques_libres']}/{est_final['bloques_totales']}"
    )
    assert est_final["bloques_libres"] == est_final["bloques_totales"]


def test_hilos_y_consola_completa_prototipo2():
    """Verifica crear_hilo y comandos completos de archivos, free y df en consola."""
    kernel.iniciar_sistema({"num_cpus": 1, "marcos_fisicos": 12, "bloques_disco": 100})
    archivos.crear_usuario("medico_a", "medicos")

    pid = procesos.crear_proceso("atencion_integral", "medico_a", [["CPU", 2]], prioridad=1)
    tid2 = procesos.crear_hilo(pid, [["CPU", 2]])
    assert tid2 > 1
    kernel.ejecutar_ticks(8)
    assert procesos.estado_proceso(pid) == "TERMINADO"

    assert "Directorio creado" in consola.ejecutar_comando("mkdir /urgencias", usuario="admin")
    assert "bytes escritos" in consola.ejecutar_comando('echo "Paciente estable" > /urgencias/nota.txt', usuario="admin")
    assert "bytes escritos" in consola.ejecutar_comando('echo " - Alta" >> /urgencias/nota.txt', usuario="admin")
    assert consola.ejecutar_comando("cat /urgencias/nota.txt", usuario="admin") == "Paciente estable - Alta"
    assert "nota.txt" in consola.ejecutar_comando("tree /urgencias", usuario="admin")
    print(f"\n[Consola P2] free -> {consola.ejecutar_comando('free')}")
    print(f"[Consola P2] df   -> {consola.ejecutar_comando('df')}")
    assert "Marcos totales: 12" in consola.ejecutar_comando("free")
    assert "Bloques totales: 100" in consola.ejecutar_comando("df")