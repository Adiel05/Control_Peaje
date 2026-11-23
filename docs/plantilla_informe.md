# Informe Técnico — Sistema Inteligente de Control de Peaje

**Autor:** Adiel (`@Adiel05`)  
**Fecha de entrega:** 25/11/2026  
**Repositorio:** https://github.com/Adiel05/Control_Peaje  
**Aplicación web:** `<URL_RENDER>`  

---

## 1. Arquitectura del sistema
- Diagrama de componentes (App Flutter → FastAPI Render HTTPS ↔ SSE → Neon PostgreSQL → Colab T4 Cloudflare Tunnel).
- Descripción del flujo de datos y separación de `INFERENCE_URL` sin dependencias locales.

## 2. Datasets y preprocesamiento (Roboflow)
| Modelo | Tarea | Clases | Imágenes totales | Propias | Universe | Aumentaciones |
|---|---|---|---|---|---|---|
| M1 | Detección de placas + OCR | `placa` | Preentrenado ONNX + 30 val | 30 | - | - |
| M2 | Segmentación vehículos | `moto`, `auto`, `minibus`, `camion`, `bus` | `<N>` | `<N>` | `<N>` | Flip, brillo, blur, rotación |
| M3 | Keypoints de ruedas | `rueda` (`centro`) | `<N>` | `<N>` | `<N>` | Flip, brillo, rotación |
| Pasajeros | Segmentación personas | `persona` | `<40-60>` | `<N>` | `<N>` | - |

## 3. Entrenamiento y métricas

### 3.1 M1 — Detección de placas + OCR
- Modelo de detección: `yolo-v9-t-384-license-plates-end2end.onnx`
- Lector OCR: `fast-plate-ocr` (`cct_xs_v2_global.onnx`) + normalización boliviana (`^\d{3,4}[A-Z]{3}$`)
- Tasa de detección (30 imágenes): `<X>%`
- Exactitud por placa completa: `<X>%`
- Exactitud por carácter: `<X>%`

### 3.2 M2 — Segmentación de instancias (`yolo11s-seg`)
- Épocas: `60`, `imgsz=640`, `batch=16`
- `box mAP@50`: `<X>`
- `mask mAP@50`: `<X>`
- `mask mAP@50-95`: `<X>`
- Tabla de mAP50 por clase (`moto`, `auto`, `minibus`, `camion`, `bus`).

### 3.3 M3 — Keypoints de ruedas (`yolo11s-pose`)
- Configuración: `kpt_shape: [1, 3]`, 1 punto `centro` por rueda
- `pose mAP@50`: `<X>`
- `box mAP@50`: `<X>`
- **MAE en conteo de ejes:** `<X>` ejes
- **Exactitud exacta en conteo de ejes:** `<X>%`

### 3.4 Identificación de pasajeros mediante segmentación (+5)
- Modelo: `yolo11s-seg` (clase `person`), máscaras opacas en evidencia (sin recortes de rostros)
- `mask mAP@50` en validación propia: `<X>`
- **MAE de conteo de pasajeros:** `<X>` personas

## 4. Gestión de entornos (+5)
- Versiones fijadas en `web/requirements.txt`, `inferencia/requirements.txt`, `entrenamiento/requirements.txt` y `movil/pubspec.lock`.
- Incluir capturas/extractos de `diagnostico_inferencia.txt`, `diagnostico_entrenamiento.txt` y `/api/v1/diagnostico`.

## 5. Latencia de punta a punta y tiempo real
- Mecanismo elegido: **Server-Sent Events (SSE)** en `/eventos` con eventos `paso`, `alerta` y `contadores`.
- Latencia promedio desglosada:
  - M1: `<X> ms` | M2: `<X> ms` | M3: `<X> ms` | Pasajeros: `<X> ms`
  - Latencia total de inferencia: `<X> ms`
  - Latencia completa App móvil → Render → Colab → Render → Panel SSE: `<X> ms`

## 6. Agente conversacional y autenticación
- Google OAuth 2.0 en web (`Authlib`) y Android (`google_sign_in` + validación `id_token` + JWT HS256).
- Lista blanca en tabla `usuarios` con roles `admin` y `operador`.
- Agente Gemini 2.5 Flash con function calling (4 estados, sugerencias OCR `O↔0, I↔1, B↔8, S↔5` y rechazo de imagen ilegible) + respaldo determinista.

## 7. Problemas encontrados y soluciones
- `<Describir 3 o 4 problemas reales que encontraste al etiquetar, entrenar o probar y cómo los resolviste>`.
