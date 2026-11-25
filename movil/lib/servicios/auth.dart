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
  static bool _inicializado = false;

  static Future<void> _asegurarInicializado() async {
    if (_inicializado) return;
    await GoogleSignIn.instance.initialize(
      serverClientId: AppConfig.webClientId.isNotEmpty ? AppConfig.webClientId : null,
    );
    _inicializado = true;
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

  /// Inicio de sesión exclusivo mediante Google Sign-In (OAuth 2.0) y validación de lista blanca.
  static Future<Map<String, dynamic>> iniciarSesionGoogle() async {
    await _asegurarInicializado();

    GoogleSignInAccount cuenta;
    try {
      cuenta = await GoogleSignIn.instance.authenticate();
    } catch (e) {
      throw AuthException('Inicio con Google cancelado o no disponible: $e');
    }

    final idToken = cuenta.authentication.idToken;
    if (idToken == null || idToken.isEmpty) {
      throw AuthException(
        'Google no devolvió idToken. Verifica GOOGLE_WEB_CLIENT_ID y la huella SHA-1 en Google Cloud.',
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
          .timeout(const Duration(seconds: 15));
    } catch (e) {
      throw AuthException('Error de conexión con el servidor ($base): $e');
    }

    if (resp.statusCode == 403) {
      try {
        await GoogleSignIn.instance.signOut();
      } catch (_) {}
      throw AuthException('Acceso denegado: esta cuenta de Google no está en la lista blanca autorizada.');
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
