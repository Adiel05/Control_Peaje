"""Agente conversacional sobre placas con Gemini (function calling) y respaldo por reglas."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import inferencia
from app.config import settings
from app.estados import consultar_estado_placa, historial_placa, resumen_caseta
from app.models import Tarifa, Usuario
from app.placas import extraer_placas_de_texto, normalizar

INSTRUCCION_SISTEMA = (
    "Eres el asistente conversacional del Sistema Inteligente de Control de Peaje. "
    "Responde siempre en español de forma clara y concisa. "
    "SOLO puedes responder con los datos reales devueltos por las herramientas o incluidos en el contexto; "
    "NUNCA inventes placas, fechas, montos, casetas ni saldos. "
    "Si el usuario menciona una placa, llama siempre a `consultar_placa`. "
    "Explica claramente uno de los cuatro estados: Registrada y con paso (indica fecha, caseta, categoría y monto), "
    "Registrada sin paso, Identificada no registrada (posible evasión), o No existe. "
    "Cuando no exista o haya errores probables de OCR, ofrece '¿Quisiste decir…?' con las sugerencias devueltas. "
    "Si no se mencionó ninguna placa ni vino imagen, pide al usuario que escriba la placa o envíe una foto."
)


def _respuesta_determinista(mensaje: str | None, estados: list[dict], placa_imagen: str | None) -> str:
    if estados:
        partes = [est["mensaje"] for est in estados]
        return "\n".join(partes)
    if placa_imagen:
        return f"Placa leída: {placa_imagen}, pero no se pudo completar la consulta."
    if mensaje and mensaje.strip():
        return (
            "No identifiqué una placa en tu consulta. Escribe una placa (ejemplo: 1234ABC) "
            "o adjunta una imagen de la placa para consultarla."
        )
    return "Envía una placa por texto o imagen para consultar su estado en el peaje."


def _llamar_gemini(
    db: Session,
    mensaje: str | None,
    historial: list[dict] | None,
    placa_imagen: str | None,
    confianza_imagen: float | None,
    estados_precalculados: list[dict],
) -> str | None:
    if not settings.gemini_api_key:
        return None

    from google import genai
    from google.genai import types

    def consultar_placa(placa: str) -> dict:
        """Consulta el estado actual de una placa en vehículos y pasos del peaje."""
        return consultar_estado_placa(db, placa)

    def historial_de_placa(placa: str, limite: int = 10) -> dict:
        """Obtiene el historial reciente de pasos por el peaje para una placa."""
        return historial_placa(db, placa, limite=limite)

    def resumen_de_caseta(caseta_id: int) -> dict:
        """Obtiene el conteo de pasos y recaudación del día de hoy para una caseta."""
        res = resumen_caseta(db, caseta_id)
        return res or {"error": f"No existe la caseta {caseta_id}"}

    def listar_tarifas() -> list[dict]:
        """Lista las tarifas vigentes en Bs por categoría de vehículo y número de ejes."""
        filas = db.execute(select(Tarifa).order_by(Tarifa.categoria.asc(), Tarifa.ejes.asc())).scalars().all()
        return [{"categoria": f.categoria, "ejes": f.ejes, "monto_bs": float(f.monto)} for f in filas]

    lineas: list[str] = []
    if historial:
        for turno in historial[-6:]:
            rol = turno.get("rol") or turno.get("role") or "usuario"
            texto = (turno.get("texto") or turno.get("content") or "").strip()
            if texto:
                lineas.append(f"{rol}: {texto}")

    if placa_imagen:
        conf_pct = f"{(confianza_imagen or 0.0) * 100:.1f}%"
        lineas.append(f"[Imagen recibida] Placa leída por M1+OCR: {placa_imagen} (confianza {conf_pct}).")

    if mensaje and mensaje.strip():
        lineas.append(f"Usuario: {mensaje.strip()}")
    elif placa_imagen:
        lineas.append(f"Usuario envió una imagen de placa ({placa_imagen}). Consulta su estado e informa al usuario.")

    if estados_precalculados:
        lineas.append(f"[Datos verificados del servidor]: {estados_precalculados}")

    prompt = "\n".join(lineas)

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCCION_SISTEMA,
            tools=[consultar_placa, historial_de_placa, resumen_de_caseta, listar_tarifas],
            temperature=0.2,
        ),
    )
    texto = getattr(resp, "text", None)
    return texto.strip() if texto and texto.strip() else None


def responder(
    db: Session,
    usuario: Usuario,
    mensaje: str | None = None,
    imagen_bytes: bytes | None = None,
    historial: list[dict] | None = None,
) -> dict:
    """Procesa consulta por texto y/o imagen y responde con estado real de la BD."""
    placa_imagen: str | None = None
    conf_imagen: float | None = None

    if imagen_bytes:
        res_inf = inferencia.inferir(db, imagen_bytes, modo="placa")
        placa_cruda = res_inf.get("placa") or res_inf.get("placa_texto_crudo") or ""
        placa_norm = normalizar(placa_cruda)
        if not placa_norm:
            return {
                "respuesta": "No pude leer una placa en la imagen. Envía otra foto más cercana y nítida.",
                "placas": [],
                "placa_detectada": None,
                "estado": "SIN_PLACA_LEGIBLE",
                "sugerencias": [],
                "fuente": "reglas",
            }
        placa_imagen = placa_norm
        conf_imagen = float(res_inf.get("confianza") or 0.0)

    candidatas: list[str] = []
    if placa_imagen:
        candidatas.append(placa_imagen)
    if mensaje:
        for p in extraer_placas_de_texto(mensaje):
            if p not in candidatas:
                candidatas.append(p)
        if not candidatas:
            limpia = normalizar(mensaje)
            if 4 <= len(limpia) <= 9 and any(c.isdigit() for c in limpia):
                candidatas.append(limpia)

    candidatas = candidatas[:3]
    estados = [consultar_estado_placa(db, cand) for cand in candidatas]

    texto_gemini: str | None = None
    try:
        texto_gemini = _llamar_gemini(
            db=db,
            mensaje=mensaje,
            historial=historial,
            placa_imagen=placa_imagen,
            confianza_imagen=conf_imagen,
            estados_precalculados=estados,
        )
    except Exception:
        texto_gemini = None

    if texto_gemini:
        respuesta_final = texto_gemini
        fuente = "gemini"
    else:
        respuesta_final = _respuesta_determinista(mensaje, estados, placa_imagen)
        fuente = "reglas"

    primero = estados[0] if estados else None
    return {
        "respuesta": respuesta_final,
        "placas": estados,
        "placa_detectada": placa_imagen or (primero["placa_normalizada"] if primero else None),
        "estado": primero["estado"] if primero else None,
        "sugerencias": primero["sugerencias"] if primero else [],
        "fuente": fuente,
    }
