# Guía de Datasets y Etiquetado en Roboflow

Esta guía resume exactamente cómo preparar los datasets en Roboflow para **M2**, **M3** y **Pasajeros (+5)** usando fotos/videos propios combinados con Roboflow Universe.

## 1. M2 — Segmentación de instancias de vehículos
- **Tipo de proyecto en Roboflow:** `Instance Segmentation`.
- **Clases exactas (5, en minúsculas y sin tildes):**
  1. `moto`
  2. `auto`
  3. `minibus`
  4. `camion`
  5. `bus`
- **Cantidad recomendada:** 150 a 300 imágenes (parte de Roboflow Universe + al menos 30%–50% de fotos/frames grabados por ti con el celular).
- **Truco rápido de etiquetado:** Usa **Label Assist / SAM (Smart Polygon)** en Roboflow y corrige los bordes manualmente.
- **Split:** 80% train / 20% valid (o 75/15/10).
- **Aumentaciones sugeridas (3x):** Flip horizontal, Brightness (±15%), Blur (hasta 1 px), Rotation (±10°).
- **Formato de exportación:** `YOLOv11` (se descarga automáticamente desde `entrenamiento/m2_segmentacion_vehiculos.ipynb`).

## 2. M3 — Keypoints de ruedas (conteo de ejes)
- **Tipo de proyecto en Roboflow:** `Keypoint Detection`.
- **Clase y esqueleto:**
  - 1 clase de objeto: `rueda` (la caja envuelve la llanta visible del lado cercano).
  - 1 keypoint dentro del esqueleto: `centro` (marcar exactamente el centro de cada rueda visible).
- **Cantidad recomendada:** 150 a 250 imágenes laterales de autos, minibuses, buses y camiones de 2, 3, 4+ ejes (combinar Roboflow Universe + frames de vehículos reales en la calle).
- **Aumentaciones sugeridas:** Brightness (±15%), Flip horizontal, Rotation (±8°). El notebook `entrenamiento/m3_keypoints_ruedas.ipynb` fuerza `kpt_shape: [1, 3]` y `flip_idx: [0]` en `data.yaml`.
- **Formato de exportación:** `YOLOv11`.

## 3. Pasajeros (+5) — Validación de segmentación de personas
- **Tipo de proyecto en Roboflow:** `Instance Segmentation`.
- **Clase:** `persona` (una sola clase).
- **Cantidad recomendada:** 40 a 60 imágenes (de vehículos con parabrisas/ventanas donde se vean 0, 1, 2 o más pasajeros) etiquetadas para validación (`valid`).
- **Privacidad:** No etiquetar rostros por separado; solo la silueta de la persona. El servidor dibuja máscaras opacas y nunca guarda recortes de rostros.
- **Formato de exportación:** `YOLOv11`, usado en `entrenamiento/pasajeros_metricas.ipynb`.

## 4. Validación M1 + OCR
- No requiere proyecto nuevo en Roboflow: toma unas **30 fotos** de placas reales/impresas y guárdalas en Google Drive dentro de `/MyDrive/peaje/validacion_placas/` nombradas con la placa real, por ejemplo `1234ABC.jpg`, `2345BCD_1.jpg`. Luego ejecuta `entrenamiento/m1_validacion_ocr.ipynb`.
