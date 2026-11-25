import 'package:shared_preferences/shared_preferences.dart';

/// Configuración de entorno inyectada con --dart-define y persistencia local.
class AppConfig {
  static const String defaultApiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://peaje-web.onrender.com',
  );

  static const String webClientId = String.fromEnvironment(
    'GOOGLE_WEB_CLIENT_ID',
    defaultValue: '',
  );

  static const String _kApiBaseKey = 'peaje_api_base_url_custom';

  /// Obtiene la URL base actual (personalizada si existe, o la predeterminada).
  static Future<String> getApiBase() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final custom = prefs.getString(_kApiBaseKey);
      if (custom != null && custom.trim().isNotEmpty) {
        return custom.trim().replaceAll(RegExp(r'/+$'), '');
      }
    } catch (_) {}
    return defaultApiBase.replaceAll(RegExp(r'/+$'), '');
  }

  /// Guarda una nueva URL base personalizada o vuelve a la predeterminada si está vacía.
  static Future<void> setApiBase(String url) async {
    final prefs = await SharedPreferences.getInstance();
    final limpia = url.trim().replaceAll(RegExp(r'/+$'), '');
    if (limpia.isEmpty || limpia == defaultApiBase.replaceAll(RegExp(r'/+$'), '')) {
      await prefs.remove(_kApiBaseKey);
    } else {
      await prefs.setString(_kApiBaseKey, limpia);
    }
  }
}
