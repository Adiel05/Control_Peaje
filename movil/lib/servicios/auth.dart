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

  static Future<Map<String, dynamic>> iniciarSesionGoogle() async {
    await _asegurarInicializado();
    final cuenta = await GoogleSignIn.instance.authenticate();
    final idToken = cuenta.authentication.idToken;
    if (idToken == null || idToken.isEmpty) {
      throw AuthException(
        'Google no devolvió idToken. Verifica GOOGLE_WEB_CLIENT_ID y el SHA-1 en Google Cloud.',
      );
    }

    final uri = Uri.parse('${AppConfig.apiBase}/api/v1/auth/google');
    final resp = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'id_token': idToken}),
    );

    if (resp.statusCode == 403) {
      await GoogleSignIn.instance.signOut();
      throw AuthException('Acceso denegado: cuenta no autorizada');
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
