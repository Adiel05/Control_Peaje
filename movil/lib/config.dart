/// Configuración de entorno inyectada con --dart-define.
class AppConfig {
  static const String apiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://peaje-web.onrender.com',
  );

  static const String webClientId = String.fromEnvironment(
    'GOOGLE_WEB_CLIENT_ID',
    defaultValue: '',
  );
}
