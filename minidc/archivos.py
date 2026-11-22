"""Sistema de archivos jerárquico con asignación indexada y permisos Unix (Prototipo 2: RF1)."""

from __future__ import annotations

from typing import Optional

from .errores import ErrorNoExiste, ErrorPermiso, ErrorSistema, ErrorYaExiste

_bloques_totales: int = 200
_tam_bloque: int = 512
_bloques_usados: set[int] = set()
_usuarios: dict[str, str] = {"admin": "admin"}
_raiz: dict = {}


def _crear_nodo_directorio(propietario: str, grupo: str, modo: str = "755") -> dict:
    return {
        "tipo": "directorio",
        "tamano": 0,
        "propietario": propietario,
        "grupo": grupo,
        "modo": modo,
        "bloques": [],
        "hijos": {},
    }


def _reiniciar_modulo(bloques_disco: int = 200, tam_bloque: int = 512) -> None:
    """Formatea el disco virtual e inicializa el usuario admin y la raíz '/'."""
    global _bloques_totales, _tam_bloque, _bloques_usados, _usuarios, _raiz

    _bloques_totales = max(1, int(bloques_disco))
    _tam_bloque = max(1, int(tam_bloque))
    _bloques_usados = set()
    _usuarios = {"admin": "admin"}
    _raiz = _crear_nodo_directorio("admin", "admin", "755")


def formatear_disco() -> None:
    """Crea el usuario admin y el directorio raíz '/' reiniciando el sistema de archivos."""
    _reiniciar_modulo(_bloques_totales, _tam_bloque)


def crear_usuario(nombre: str, grupo: str = "usuarios") -> None:
    """Registra un nuevo usuario en el sistema."""
    if not nombre:
        raise ErrorSistema("El nombre de usuario no puede estar vacío.")
    if nombre in _usuarios:
        raise ErrorYaExiste(f"El usuario '{nombre}' ya existe.")
    _usuarios[nombre] = grupo


def _validar_usuario(usuario: str) -> str:
    if usuario not in _usuarios:
        raise ErrorNoExiste(f"El usuario '{usuario}' no existe.")
    return _usuarios[usuario]


def _validar_modo_octal(modo: str) -> str:
    m = str(modo).strip()
    if len(m) != 3 or any(c not in "01234567" for c in m):
        raise ErrorSistema(f"Modo de permisos octal inválido: {modo!r}")
    return m


def _verificar_permiso(nodo: dict, usuario: str, accion: str) -> None:
    """Verifica permisos Unix (r=4, w=2, x=1) para propietario, grupo y otros. admin los ignora."""
    _validar_usuario(usuario)
    if usuario == "admin":
        return

    modo = nodo["modo"]
    grupo_usuario = _usuarios[usuario]

    if usuario == nodo["propietario"]:
        digito = int(modo[0])
    elif grupo_usuario == nodo["grupo"]:
        digito = int(modo[1])
    else:
        digito = int(modo[2])

    mascaras = {"r": 4, "w": 2, "x": 1}
    if (digito & mascaras[accion]) == 0:
        raise ErrorPermiso(
            f"Permiso denegado ({accion}) para el usuario '{usuario}' sobre recurso modo {modo}."
        )


def _normalizar_partes(ruta: str) -> list[str]:
    if not ruta or not ruta.startswith("/"):
        raise ErrorSistema(f"La ruta debe ser absoluta (empezar por '/'): {ruta!r}")
    partes = [p for p in ruta.split("/") if p and p != "."]
    resultado: list[str] = []
    for p in partes:
        if p == "..":
            if resultado:
                resultado.pop()
        else:
            resultado.append(p)
    return resultado


def _combinar_ruta(base_partes: list[str], destino: str) -> list[str]:
    if destino.startswith("/"):
        return _normalizar_partes(destino)
    combinadas = list(base_partes)
    for p in destino.split("/"):
        if not p or p == ".":
            continue
        if p == "..":
            if combinadas:
                combinadas.pop()
        else:
            combinadas.append(p)
    return combinadas


def _buscar_nodo(ruta: str, seguir_ultimo_enlace: bool = True, profundidad: int = 0) -> tuple[dict, Optional[dict], str]:
    """Navega el árbol de directorios y devuelve (nodo, padre, nombre_final)."""
    if profundidad > 16:
        raise ErrorSistema("Demasiados niveles de enlaces simbólicos (bucle detectado).")

    partes = _normalizar_partes(ruta)
    if not partes:
        return _raiz, None, "/"

    actual = _raiz
    padre: Optional[dict] = None

    for idx, nombre in enumerate(partes):
        es_ultimo = idx == (len(partes) - 1)
        if actual["tipo"] != "directorio":
            raise ErrorNoExiste(f"Componente de ruta no es un directorio: '{nombre}'.")
        if nombre not in actual["hijos"]:
            raise ErrorNoExiste(f"La ruta '{ruta}' no existe.")

        padre = actual
        actual = actual["hijos"][nombre]

        if actual["tipo"] == "enlace" and (not es_ultimo or seguir_ultimo_enlace):
            destino_partes = _combinar_ruta(partes[:idx], actual["destino"])
            ruta_destino = "/" + "/".join(destino_partes)
            return _buscar_nodo(ruta_destino, seguir_ultimo_enlace=True, profundidad=profundidad + 1)

    return actual, padre, partes[-1]


def _obtener_padre_y_nombre(ruta: str) -> tuple[dict, str, list[str]]:
    """Resuelve el directorio padre donde se creará un nuevo nodo."""
    partes = _normalizar_partes(ruta)
    if not partes:
        raise ErrorYaExiste("El directorio raíz '/' ya existe.")
    nombre = partes[-1]
    ruta_padre = "/" + "/".join(partes[:-1])
    padre, _, _ = _buscar_nodo(ruta_padre, seguir_ultimo_enlace=True)
    if padre["tipo"] != "directorio":
        raise ErrorSistema(f"El destino padre '{ruta_padre}' no es un directorio.")
    return padre, nombre, partes


def _asignar_bloques(cantidad: int) -> list[int]:
    """Asigna bloques libres mediante política indexada garantizando el invariante de disco."""
    if cantidad == 0:
        return []
    disponibles = _bloques_totales - len(_bloques_usados)
    if cantidad > disponibles:
        raise ErrorSistema(
            f"Espacio insuficiente en disco: se requieren {cantidad} bloques y hay {disponibles}."
        )
    asignados: list[int] = []
    for b in range(_bloques_totales):
        if b not in _bloques_usados:
            _bloques_usados.add(b)
            asignados.append(b)
            if len(asignados) == cantidad:
                break
    return asignados


def _liberar_bloques(bloques: list[int]) -> None:
    for b in bloques:
        _bloques_usados.discard(b)


def fs_mkdir(ruta: str, usuario: str) -> None:
    """Crea un nuevo directorio verificando permisos de escritura en el padre."""
    grupo = _validar_usuario(usuario)
    padre, nombre, _ = _obtener_padre_y_nombre(ruta)
    _verificar_permiso(padre, usuario, "w")

    if nombre in padre["hijos"]:
        raise ErrorYaExiste(f"Ya existe '{nombre}' en el directorio destino.")

    padre["hijos"][nombre] = _crear_nodo_directorio(usuario, grupo, "755")


def fs_escribir(ruta: str, contenido: str, usuario: str, agregar: bool = False) -> int:
    """Crea o escribe en un archivo y devuelve la cantidad de bytes escritos."""
    grupo = _validar_usuario(usuario)
    datos_nuevos = str(contenido)
    bytes_escritos = len(datos_nuevos.encode("utf-8"))

    try:
        nodo, _, _ = _buscar_nodo(ruta, seguir_ultimo_enlace=True)
        if nodo["tipo"] != "archivo":
            raise ErrorSistema(f"'{ruta}' no es un archivo regular.")
        _verificar_permiso(nodo, usuario, "w")

        texto_final = (nodo["contenido"] + datos_nuevos) if agregar else datos_nuevos
        tam_final = len(texto_final.encode("utf-8"))
        bloques_req = (tam_final + _tam_bloque - 1) // _tam_bloque if tam_final > 0 else 0

        bloques_previos = list(nodo["bloques"])
        _liberar_bloques(bloques_previos)
        try:
            nuevos_bloques = _asignar_bloques(bloques_req)
        except ErrorSistema:
            for b in bloques_previos:
                _bloques_usados.add(b)
            raise

        nodo["contenido"] = texto_final
        nodo["tamano"] = tam_final
        nodo["bloques"] = nuevos_bloques
        return bytes_escritos

    except ErrorNoExiste:
        # Si la ruta es un enlace simbólico roto, no crear encima como archivo nuevo
        try:
            enlace, _, _ = _buscar_nodo(ruta, seguir_ultimo_enlace=False)
            if enlace["tipo"] == "enlace":
                raise ErrorNoExiste(f"El destino del enlace simbólico '{ruta}' no existe.")
        except ErrorNoExiste:
            pass

        padre, nombre, _ = _obtener_padre_y_nombre(ruta)
        _verificar_permiso(padre, usuario, "w")

        tam_final = bytes_escritos
        bloques_req = (tam_final + _tam_bloque - 1) // _tam_bloque if tam_final > 0 else 0
        nuevos_bloques = _asignar_bloques(bloques_req)

        padre["hijos"][nombre] = {
            "tipo": "archivo",
            "contenido": datos_nuevos,
            "tamano": tam_final,
            "propietario": usuario,
            "grupo": grupo,
            "modo": "644",
            "bloques": nuevos_bloques,
        }
        return bytes_escritos


def fs_leer(ruta: str, usuario: str) -> str:
    """Lee y devuelve el contenido de un archivo verificando permisos de lectura."""
    _validar_usuario(usuario)
    nodo, _, _ = _buscar_nodo(ruta, seguir_ultimo_enlace=True)
    if nodo["tipo"] != "archivo":
        raise ErrorSistema(f"'{ruta}' no es un archivo regular.")
    _verificar_permiso(nodo, usuario, "r")
    return nodo["contenido"]


def fs_listar(ruta: str, usuario: str) -> list:
    """Lista los nombres de entradas de un directorio (o el nombre del archivo)."""
    _validar_usuario(usuario)
    nodo, _, nombre = _buscar_nodo(ruta, seguir_ultimo_enlace=True)
    if nodo["tipo"] == "directorio":
        _verificar_permiso(nodo, usuario, "r")
        return sorted(nodo["hijos"].keys())
    _verificar_permiso(nodo, usuario, "r")
    return [nombre]


def _liberar_subarbol(nodo: dict) -> None:
    if nodo["tipo"] == "archivo":
        _liberar_bloques(nodo["bloques"])
    elif nodo["tipo"] == "directorio":
        for hijo in nodo["hijos"].values():
            _liberar_subarbol(hijo)


def fs_eliminar(ruta: str, usuario: str, recursivo: bool = False) -> None:
    """Elimina un archivo, enlace simbólico o directorio y libera sus bloques."""
    _validar_usuario(usuario)
    nodo, padre, nombre = _buscar_nodo(ruta, seguir_ultimo_enlace=False)
    if padre is None:
        raise ErrorPermiso("No se puede eliminar el directorio raíz '/'.")

    _verificar_permiso(padre, usuario, "w")

    if nodo["tipo"] == "directorio" and nodo["hijos"] and not recursivo:
        raise ErrorSistema(f"El directorio '{ruta}' no está vacío; use recursivo=True.")

    _liberar_subarbol(nodo)
    del padre["hijos"][nombre]


def fs_chmod(ruta: str, modo: str, usuario: str) -> None:
    """Cambia los permisos octales de un archivo o directorio (solo propietario o admin)."""
    _validar_usuario(usuario)
    modo_ok = _validar_modo_octal(modo)
    nodo, _, _ = _buscar_nodo(ruta, seguir_ultimo_enlace=True)

    if usuario != "admin" and usuario != nodo["propietario"]:
        raise ErrorPermiso(f"Solo el propietario o admin pueden cambiar permisos de '{ruta}'.")

    nodo["modo"] = modo_ok


def fs_enlace_simbolico(destino: str, ruta_enlace: str, usuario: str) -> None:
    """Crea un enlace simbólico apuntando a 'destino' en 'ruta_enlace'."""
    grupo = _validar_usuario(usuario)
    padre, nombre, _ = _obtener_padre_y_nombre(ruta_enlace)
    _verificar_permiso(padre, usuario, "w")

    if nombre in padre["hijos"]:
        raise ErrorYaExiste(f"La ruta de enlace '{ruta_enlace}' ya existe.")

    padre["hijos"][nombre] = {
        "tipo": "enlace",
        "destino": str(destino),
        "tamano": len(str(destino).encode("utf-8")),
        "propietario": usuario,
        "grupo": grupo,
        "modo": "777",
        "bloques": [],
    }


def fs_info(ruta: str) -> dict:
    """Devuelve los metadatos de un archivo, directorio o enlace simbólico."""
    nodo, _, _ = _buscar_nodo(ruta, seguir_ultimo_enlace=False)
    return {
        "tipo": nodo["tipo"],
        "tamano": nodo["tamano"],
        "propietario": nodo["propietario"],
        "grupo": nodo["grupo"],
        "modo": nodo["modo"],
        "bloques": list(nodo["bloques"]),
    }


def fs_estado_disco() -> dict:
    """Devuelve el estado de bloques totales, libres y cantidad de huecos contiguos."""
    usados = len(_bloques_usados)
    libres = _bloques_totales - usados

    huecos = 0
    en_hueco = False
    for b in range(_bloques_totales):
        if b not in _bloques_usados:
            if not en_hueco:
                huecos += 1
                en_hueco = True
        else:
            en_hueco = False

    return {
        "bloques_totales": _bloques_totales,
        "bloques_libres": libres,
        "huecos_libres": huecos,
    }


def politica_asignacion_archivos() -> str:
    """Nombre de la política de asignación de bloques implementada."""
    return "Indexada"


def _validar_acceso_directorio(ruta: str, usuario: str) -> str:
    """Valida que 'ruta' exista, sea un directorio y el usuario tenga permiso de ejecución."""
    _validar_usuario(usuario)
    partes = _normalizar_partes(ruta)
    ruta_norm = "/" + "/".join(partes)
    nodo, _, _ = _buscar_nodo(ruta_norm, seguir_ultimo_enlace=True)
    if nodo["tipo"] != "directorio":
        raise ErrorSistema(f"'{ruta}' no es un directorio.")
    _verificar_permiso(nodo, usuario, "x")
    return ruta_norm