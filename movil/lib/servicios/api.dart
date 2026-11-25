import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'auth.dart';

class SesionExpiradaException implements Exception {}

class ApiService {
  static Future<Map<String, String>> _headers() async {
    final token = await AuthService.obtenerToken();
    if (token == null || token.isEmpty) {
      throw SesionExpiradaException();
    }
    return {'Authorization': 'Bearer $token'};
  }

  static void _verificar401(int statusCode) {
    if (statusCode == 401) {
      throw SesionExpiradaException();
    }
  }

  /// Verifica el estado de salud y latencia del backend.
  static Future<Map<String, dynamic>> probarConexion([String? customBase]) async {
    final base = customBase ?? await AppConfig.getApiBase();
    final uri = Uri.parse('$base/login');
    final stopwatch = Stopwatch()..start();
    final resp = await http.get(uri).timeout(const Duration(seconds: 10));
    stopwatch.stop();
    return {
      'ok': resp.statusCode == 200,
      'status': resp.statusCode,
      'latencia_ms': stopwatch.elapsedMilliseconds,
      'base': base,
    };
  }

  /// Actualiza la URL del túnel de inferencia (Colab) directamente desde la app.
  static Future<Map<String, dynamic>> actualizarUrlInferencia(String url) async {
    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/estado/inferencia');
    final headers = await _headers();
    headers['Content-Type'] = 'application/json';
    final resp = await http
        .post(uri, headers: headers, body: jsonEncode({'inference_url': url.trim()}))
        .timeout(const Duration(seconds: 15));
    _verificar401(resp.statusCode);
    if (resp.statusCode != 200) {
      throw Exception('HTTP ${resp.statusCode}: ${resp.body}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<List<Map<String, dynamic>>> casetas() async {
    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/casetas');
    final resp = await http.get(uri, headers: await _headers());
    _verificar401(resp.statusCode);
    if (resp.statusCode != 200) {
      throw Exception('Error al listar casetas: HTTP ${resp.statusCode}');
    }
    final lista = jsonDecode(resp.body) as List<dynamic>;
    return lista.cast<Map<String, dynamic>>();
  }

  static Future<Map<String, dynamic>> enviarFrame(Uint8List bytes, int casetaId) async {
    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/pasos/frame');
    final req = http.MultipartRequest('POST', uri)
      ..headers.addAll(await _headers())
      ..fields['caseta_id'] = casetaId.toString()
      ..files.add(http.MultipartFile.fromBytes('imagen', bytes, filename: 'frame.jpg'));

    final streamed = await req.send();
    final resp = await http.Response.fromStream(streamed);
    _verificar401(resp.statusCode);
    if (resp.statusCode != 200) {
      throw Exception('Error al enviar frame: HTTP ${resp.statusCode}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> consultarPlaca(String placa) async {
    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/placas/consultar');
    final headers = await _headers();
    headers['Content-Type'] = 'application/json';
    final resp = await http.post(
      uri,
      headers: headers,
      body: jsonEncode({'placa': placa}),
    );
    _verificar401(resp.statusCode);
    if (resp.statusCode != 200) {
      throw Exception('Error al consultar placa: HTTP ${resp.statusCode}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> chat({
    String? mensaje,
    Uint8List? imagenBytes,
    List<Map<String, String>>? historial,
  }) async {
    final base = await AppConfig.getApiBase();
    final uri = Uri.parse('$base/api/v1/agente/chat');
    final req = http.MultipartRequest('POST', uri)..headers.addAll(await _headers());
    if (mensaje != null && mensaje.trim().isNotEmpty) {
      req.fields['mensaje'] = mensaje.trim();
    }
    if (historial != null && historial.isNotEmpty) {
      req.fields['historial'] = jsonEncode(historial);
    }
    if (imagenBytes != null && imagenBytes.isNotEmpty) {
      req.files.add(http.MultipartFile.fromBytes('imagen', imagenBytes, filename: 'placa.jpg'));
    }

    final streamed = await req.send();
    final resp = await http.Response.fromStream(streamed);
    _verificar401(resp.statusCode);
    if (resp.statusCode != 200) {
      throw Exception('Error del agente: HTTP ${resp.statusCode}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }
}
