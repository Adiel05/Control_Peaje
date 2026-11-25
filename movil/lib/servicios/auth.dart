import 'dart:convert';

import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

class AuthException implements Exception {
  final String mensaje;
  AuthException(this.mensaje);

  @override
  String toString() => mensaje;
}

class AuthService {
  static const _kTokenKey = 'peaje_jwt';
  static const _kUsuarioKey = 'peaje_usuario';
  static const _kUltimoEmailKey = 'peaje_ultimo_admin_email';
  static const String emailAdminDefault = 'noelpabonnina@gmail.com';

  static bool _inicializado = false;

  static Future<void> _asegurarInicializado() async {
    if (_inicializado) return;
    try {
      await GoogleSignIn.instance.initialize(
        serverClientId: AppConfig.webClientId.isNotEmpty ? AppConfig.webClientId : null,
      );
      _inicializado = true;
    } catch (_) {}
  }

  static Future<String?> obtenerToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kTokenKey);
  }

  static Future<Map<String, dynamic>?> obtenerUsuario() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kUsuarioKey);
    if (raw == null || raw.isEmpty) return null;
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  static Future<String> obtenerUltimoEmailAdmin() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kUltimoEmailKey) ?? emailAdminDefault;
  }

  static Future<void> guardarUltimoEmailAdmin(String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUltimoEmailKey, email.trim().toLowerCase());
  }

  /// Inicio de sesión directo y verificado para administradores autorizados.
  /// Evita el bloqueo del código [16] de Google Play Services por certificado SHA-1 en APK externa.
  static Future<Map<String, dynamic>> iniciarSesionDirecta(String email) async {
    final emailLimpio = email.trim().toLowerCase();
    if (emailLimpio.isEmpty) {
      throw AuthException('Debes ingresar un correo electrónico');
    }

    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/auth/admin-directo');

    http.Response resp;
    try {
      resp = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'email': emailLimpio}),
          )
          .timeout(const Duration(seconds: 12));
    } catch (e) {
      throw AuthException(
        'No se pudo conectar al servidor ($base). Verifica tu conexión o el estado de Render: $e',
      );
    }

    if (resp.statusCode == 403) {
      throw AuthException(
        'Acceso denegado: El correo "$emailLimpio" no está en la lista de administradores autorizados.',
      );
    }

    if (resp.statusCode != 200) {
      throw AuthException(
        'Error del servidor (${resp.statusCode}): ${resp.body}',
      );
    }

    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final token = data['access_token'] as String;
    final usuario = data['usuario'] as Map<String, dynamic>;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kTokenKey, token);
    await prefs.setString(_kUsuarioKey, jsonEncode(usuario));
    await guardarUltimoEmailAdmin(emailLimpio);

    return usuario;
  }

  /// Inicio de sesión estándar mediante Google Sign-In SDK.
  static Future<Map<String, dynamic>> iniciarSesionGoogle() async {
    await _asegurarInicializado();

    GoogleSignInAccount cuenta;
    try {
      cuenta = await GoogleSignIn.instance.authenticate();
    } catch (e) {
      final strErr = e.toString();
      if (strErr.contains('[16]') || strErr.contains('reauth failed') || strErr.contains('canceled')) {
        throw AuthException(
          'Google Sign-In Error [16]: Falta vincular la huella digital SHA-1 en Google Cloud Console.\n\n👉 Utiliza el botón "Acceso Directo Administrador" para ingresar inmediatamente sin este requisito.',
        );
      }
      throw AuthException('Error al autenticar con Google: $e');
    }

    final idToken = cuenta.authentication.idToken;
    if (idToken == null || idToken.isEmpty) {
      throw AuthException(
        'Google no devolvió token de sesión (idToken). Usa el acceso directo de administrador.',
      );
    }

    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/auth/google');

    http.Response resp;
    try {
      resp = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'id_token': idToken}),
          )
          .timeout(const Duration(seconds: 12));
    } catch (e) {
      throw AuthException('Error de conexión con el backend: $e');
    }

    if (resp.statusCode == 403) {
      try {
        await GoogleSignIn.instance.signOut();
      } catch (_) {}
      throw AuthException(
        'Acceso denegado: La cuenta de Google no pertenece a los administradores autorizados.',
      );
    }

    if (resp.statusCode != 200) {
      throw AuthException('Error de autenticación (${resp.statusCode}): ${resp.body}');
    }

    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final token = data['access_token'] as String;
    final usuario = data['usuario'] as Map<String, dynamic>;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kTokenKey, token);
    await prefs.setString(_kUsuarioKey, jsonEncode(usuario));
    return usuario;
  }

  static Future<void> cerrarSesion() async {
    try {
      await _asegurarInicializado();
      await GoogleSignIn.instance.signOut();
    } catch (_) {}
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kTokenKey);
    await prefs.remove(_kUsuarioKey);
  }
}
