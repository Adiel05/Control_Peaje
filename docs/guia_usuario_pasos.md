# Lista de tareas del usuario (paso a paso hasta la entrega)

Sigue estos pasos en orden. Todo el código ya está listo; aquí solo configuras tus cuentas en la nube, entrenas los modelos con tus imágenes y grabas la demostración.

## 1. GitHub (repositorio público)
- Entra a `https://github.com/Adiel05/Control_Peaje` → **Settings** → **Danger Zone** → **Change repository visibility** → **Make public** (necesario para que Google Colab haga `git clone` sin contraseña).

## 2. Google Cloud Console (OAuth 2.0)
1. Crea un proyecto nuevo (ej. `control-peaje-ia`).
2. Ve a **APIs y servicios → Pantalla de consentimiento de OAuth**:
   - Tipo: **Externo**.
   - En **Usuarios de prueba (Test users)** agrega **tu correo de Gmail** y **`doc.alvaro.pinto.ma@unifranz.edu.bo`** (o publica la app).
3. Ve a **Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - **Cliente 1 — Aplicación web:**
     - Orígenes autorizados de JavaScript: `https://<tu-app>.onrender.com` y `http://localhost:8000`
     - URIs de redireccionamiento autorizados: `https://<tu-app>.onrender.com/auth/callback` y `http://localhost:8000/auth/callback`
     - Guarda el **Client ID** y el **Client Secret**.
   - **Cliente 2 — Android:**
     - Nombre del paquete: `com.controlpeaje.control_peaje`
     - Huella digital del certificado **SHA-1** (clave debug local):
       `75:F5:CD:57:D9:72:77:39:09:C3:2C:9B:F8:23:4A:87:26:15:4D:52`
4. **Importante:** la app Flutter usa el **Client ID Web** (el del Cliente 1) en `--dart-define=GOOGLE_WEB_CLIENT_ID=...` para poder obtener el `id_token` que valida el backend.

## 3. Neon (PostgreSQL gratis y persistente)
1. Crea un proyecto gratuito en [neon.tech](https://neon.tech).
2. Copia la **Connection String** (debe terminar en `?sslmode=require`), por ejemplo:
   `postgresql://usuario:clave@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require`

## 4. Google AI Studio (Gemini API Key)
1. Entra a [aistudio.google.com](https://aistudio.google.com) → **Get API key** → **Create API key**.
2. Guárdala para Render (`GEMINI_API_KEY`).

## 5. Render (aplicación web en subdominio HTTPS)
1. Entra a [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**.
2. Selecciona el repositorio `Adiel05/Control_Peaje` y la rama `develop` (`render.yaml` configura `rootDir: web`).
3. Carga las variables de entorno en Render:
   - `DATABASE_URL`: la URL de Neon (`?sslmode=require`)
   - `GOOGLE_CLIENT_ID`: Client ID **Web** de Google Cloud
   - `GOOGLE_CLIENT_SECRET`: Client Secret **Web** de Google Cloud
   - `BASE_URL`: `https://<tu-app>.onrender.com` (sin barra final)
   - `ADMIN_EMAILS`: `doc.alvaro.pinto.ma@unifranz.edu.bo,tu_correo@gmail.com`
   - `INFERENCE_API_KEY`: inventa una clave larga (ej. 32+ caracteres aleatorios)
   - `GEMINI_API_KEY`: tu clave de Google AI Studio
   - `INFERENCE_URL`: deja `mock` inicialmente (luego se cambia desde `/estado`)
4. Espera el despliegue y verifica que abre `https://<tu-app>.onrender.com/docs` y puedes iniciar sesión en `/login` con Google.

## 6. UptimeRobot (evitar que Render free se duerma)
1. Crea un monitor HTTP(s) gratuito en [uptimerobot.com](https://uptimerobot.com).
2. URL: `https://<tu-app>.onrender.com/login` cada **5 minutos**.

## 7. Roboflow (datasets propios + Universe)
- Sigue [`docs/guia_datasets_roboflow.md`](guia_datasets_roboflow.md) para crear y etiquetar:
  1. Proyecto M2 (`Instance Segmentation`, 5 clases: `moto`, `auto`, `minibus`, `camion`, `bus`).
  2. Proyecto M3 (`Keypoint Detection`, clase `rueda`, keypoint `centro`).
  3. Proyecto Pasajeros (`Instance Segmentation`, clase `persona`, 40–60 imágenes de validación).
- Anota las URLs públicas de los 3 datasets para `README.md` y el informe.

## 8. Google Colab — Secrets
En Colab (icono de llave **Secrets** en el panel izquierdo), agrega y habilita para los notebooks:
1. `ROBOFLOW_API_KEY`: tu API key privada de Roboflow.
2. `INFERENCE_API_KEY`: exactamente el mismo valor que pusiste en Render.

## 9. Google Colab — Entrenamiento y métricas
Ejecuta con GPU T4 los notebooks en `/entrenamiento`:
1. `m2_segmentacion_vehiculos.ipynb` (edita `WORKSPACE`, `PROYECTO`, `VERSION`) → guarda `m2_seg.pt` y `metricas_m2.json` en Drive.
2. `m3_keypoints_ruedas.ipynb` (edita `WORKSPACE`, `PROYECTO`, `VERSION`) → guarda `m3_pose.pt` y `metricas_m3.json` en Drive.
3. Sube ~30 fotos de placas a `/MyDrive/peaje/validacion_placas/` nombradas `1234ABC.jpg`, etc., y ejecuta `m1_validacion_ocr.ipynb` → guarda `metricas_m1.json` y `metricas_m1_ocr.csv`.
4. `pasajeros_metricas.ipynb` → guarda `metricas_pasajeros.json` en Drive.

## 10. Google Colab — Servidor de inferencia en vivo
1. Abre `inferencia/servidor_colab.ipynb` con GPU T4 y ejecuta las celdas en orden.
2. Copia la URL `https://xxxx.trycloudflare.com` que imprime la celda del túnel.
3. En tu web (`https://<tu-app>.onrender.com/estado`) pégala en **Actualizar INFERENCE_URL** y guarda.
4. Verifica que `/estado` muestra **Respondiendo** y `"fuente_m2": "propio"`.

## 11. Vehículos de prueba para la grabación
1. Entra a `/vehiculos` como administrador.
2. Registra las placas reales de los vehículos/impresiones que vas a filmar (con saldo positivo).
3. Deja al menos **una placa sin registrar** (dispara alerta `NO_REGISTRADA`) y usa `3456CDE` o una con saldo `0` para mostrar `SIN_SALDO`.

## 12. Compilar e instalar la APK en tu teléfono
En `d:\PracticaIA\Control_Peaje\movil`:
```powershell
D:\Herramientas\flutter_windows_3.47.7-stable\flutter\bin\flutter.bat build apk --release `
  --dart-define=API_BASE_URL=https://<tu-app>.onrender.com `
  --dart-define=GOOGLE_WEB_CLIENT_ID=<TU_CLIENT_ID_WEB>.apps.googleusercontent.com
```
El archivo quedará en `movil\build\app\outputs\flutter-apk\app-release.apk`. Instálalo en tu celular y súbelo también a la carpeta de Drive.

## 13. Video demostración (8–12 min) y carpeta en la nube
- Graba cumpliendo la sección 8 del enunciado:
  1. Presentación personal y arquitectura (máx. 1 min).
  2. Login con Google en web y app, incluyendo rechazo de una cuenta **no** incluida en la lista blanca.
  3. App móvil en modo **Caseta** filmando video real y mostrando placa, categoría, ejes, tarifa y pasajeros.
  4. Pantalla dividida con el panel web recibiendo el paso en tiempo real (SSE, sin recargar) y mostrando al menos un caso con **varios pasajeros**.
  5. Alerta en tiempo real cuando pasa una placa **no registrada**.
  6. Agente conversacional respondiendo los **4 estados** (`1234ABC` con paso, `7890GHI` sin paso, `9999ZZZ` identificada no registrada, y una inexistente como `I234A8C` que sugiera `¿Quisiste decir 1234ABC?`) usando al menos **texto e imagen**.
  7. Consola de Google Colab en ejecución.
  8. Métricas principales y conclusiones.
- Completa el informe PDF usando [`docs/plantilla_informe.md`](plantilla_informe.md).
- Sube a Drive (con permiso de lectura para el docente): video, informe PDF, APK, capturas de pantalla, `docs/openapi.json`, `diagnostico_*.txt` y los `metricas_*.json`.
- Actualiza los enlaces pendientes en [`README.md`](../README.md) y entrega los 3 enlaces en Moodle (GitHub, Drive y subdominio HTTPS).
