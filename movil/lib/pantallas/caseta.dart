import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../servicios/api.dart';

class CasetaPantalla extends StatefulWidget {
  final VoidCallback onSesionExpirada;
  const CasetaPantalla({super.key, required this.onSesionExpirada});

  @override
  State<CasetaPantalla> createState() => _CasetaPantallaState();
}

class _CasetaPantallaState extends State<CasetaPantalla> {
  CameraController? _camara;
  bool _camaraLista = false;
  bool _capturando = false;
  Timer? _timer;
  int _enVuelo = 0;
  int _enviados = 0;
  DateTime? _inicioCaptura;

  List<Map<String, dynamic>> _casetas = [];
  int? _casetaId;
  Map<String, dynamic>? _ultimoPaso;
  Map<String, dynamic>? _ultimaDeteccion;
  Uint8List? _ultimaImagenAnotada;
  bool _verIaEnVivo = true;
  bool _esMock = false;
  String? _avisoInferencia;
  String _estadoInfo = 'Listo para capturar';

  @override
  void initState() {
    super.initState();
    _cargarCasetas();
    _iniciarCamara();
  }

  Future<void> _cargarCasetas() async {
    try {
      final lista = await ApiService.casetas();
      if (!mounted) return;
      setState(() {
        _casetas = lista;
        if (lista.isNotEmpty) _casetaId = lista.first['id'] as int;
      });
    } on SesionExpiradaException {
      widget.onSesionExpirada();
    } catch (e) {
      if (mounted) setState(() => _estadoInfo = 'Error casetas: $e');
    }
  }

  Future<void> _iniciarCamara() async {
    try {
      final cams = await availableCameras();
      if (cams.isEmpty) {
        if (mounted) setState(() => _estadoInfo = 'No se encontró cámara');
        return;
      }
      final trasera = cams.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cams.first,
      );
      final ctrl = CameraController(trasera, ResolutionPreset.medium, enableAudio: false);
      await ctrl.initialize();
      if (!mounted) {
        await ctrl.dispose();
        return;
      }
      setState(() {
        _camara = ctrl;
        _camaraLista = true;
      });
    } catch (e) {
      if (mounted) setState(() => _estadoInfo = 'Error cámara: $e');
    }
  }

  Uint8List? _decodificarBase64(dynamic dataUrl) {
    if (dataUrl is! String || dataUrl.isEmpty) return null;
    try {
      final idx = dataUrl.indexOf(',');
      final b64 = idx >= 0 ? dataUrl.substring(idx + 1) : dataUrl;
      return base64Decode(b64);
    } catch (_) {
      return null;
    }
  }

  void _alternarCaptura() {
    if (_capturando) {
      _timer?.cancel();
      _timer = null;
      setState(() {
        _capturando = false;
        _estadoInfo = 'Captura detenida';
      });
      return;
    }

    if (!_camaraLista || _casetaId == null) return;
    _inicioCaptura = DateTime.now();
    _enviados = 0;
    setState(() {
      _capturando = true;
      _estadoInfo = 'Capturando ~2.5 fps...';
    });

    _timer = Timer.periodic(const Duration(milliseconds: 450), (_) => _tickFrame());
  }

  Future<void> _tickFrame() async {
    if (!_capturando || _camara == null || !_camara!.value.isInitialized) return;
    if (_enVuelo >= 1 || _camara!.value.isTakingPicture) return;
    final caseta = _casetaId;
    if (caseta == null) return;

    _enVuelo++;
    try {
      final xfile = await _camara!.takePicture();
      final bytes = await xfile.readAsBytes();
      final resp = await ApiService.enviarFrame(bytes, caseta);
      if (!mounted) return;
      _enviados++;

      final anotadaBytes = _decodificarBase64(resp['imagen_anotada']);

      setState(() {
        if (anotadaBytes != null) {
          _ultimaImagenAnotada = anotadaBytes;
        }
        _esMock = resp['mock'] == true;
        _avisoInferencia = resp['aviso']?.toString();
        _ultimaDeteccion = resp;

        if (resp['registrado'] == true) {
          _ultimoPaso = resp;
          _estadoInfo = 'Registrado: ${resp['placa']} (${resp['estado']})';
        } else {
          final placaStr = resp['placa'] != null && resp['placa'].toString().isNotEmpty
              ? ' · ${resp['placa']}'
              : '';
          _estadoInfo = 'En vivo: ${resp['motivo'] ?? 'analizando'}$placaStr';
        }
      });
    } on SesionExpiradaException {
      _timer?.cancel();
      widget.onSesionExpirada();
    } catch (e) {
      if (mounted) setState(() => _estadoInfo = 'Error envío: $e');
    } finally {
      _enVuelo--;
    }
  }

  Color _colorEstado(String? estado) {
    if (estado == 'OK') return Colors.green;
    if (estado == 'SIN_SALDO') return Colors.orange;
    return Colors.red;
  }

  double _aspectRatioCamara() {
    if (_camara == null || !_camara!.value.isInitialized) return 3 / 4;
    final ar = _camara!.value.aspectRatio;
    // En modo vertical, el sensor reporta ancho/alto > 1; invertimos para no estirar.
    return ar > 1.0 ? (1.0 / ar) : ar;
  }

  @override
  void dispose() {
    _timer?.cancel();
    _camara?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final segs = _inicioCaptura == null
        ? 0.0
        : DateTime.now().difference(_inicioCaptura!).inMilliseconds / 1000.0;
    final fpsReales = segs > 0.5 ? (_enviados / segs) : 0.0;

    final mostrarAnotada = _verIaEnVivo && _ultimaImagenAnotada != null;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<int>(
            initialValue: _casetaId,
            decoration: const InputDecoration(labelText: 'Caseta de peaje', border: OutlineInputBorder()),
            items: _casetas
                .map((c) => DropdownMenuItem<int>(
                      value: c['id'] as int,
                      child: Text(c['nombre'].toString()),
                    ))
                .toList(),
            onChanged: _capturando ? null : (v) => setState(() => _casetaId = v),
          ),
          const SizedBox(height: 10),

          // Selector de vista y estado del motor IA
          Row(
            children: [
              Expanded(
                child: SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment<bool>(
                      value: true,
                      icon: Icon(Icons.auto_awesome, size: 16),
                      label: Text('IA en vivo', style: TextStyle(fontSize: 12)),
                    ),
                    ButtonSegment<bool>(
                      value: false,
                      icon: Icon(Icons.videocam, size: 16),
                      label: Text('Cámara', style: TextStyle(fontSize: 12)),
                    ),
                  ],
                  selected: {_verIaEnVivo},
                  onSelectionChanged: (s) => setState(() => _verIaEnVivo = s.first),
                ),
              ),
              const SizedBox(width: 8),
              if (_ultimaDeteccion != null)
                Chip(
                  avatar: Icon(
                    _esMock ? Icons.warning_amber_rounded : Icons.check_circle,
                    color: Colors.white,
                    size: 16,
                  ),
                  label: Text(
                    _esMock ? 'Mock' : 'IA Colab',
                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                  ),
                  backgroundColor: _esMock ? Colors.orange.shade700 : Colors.green.shade700,
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
          const SizedBox(height: 8),

          // Visor sin estiramiento (mantiene relación de aspecto real)
          Container(
            constraints: const BoxConstraints(maxHeight: 340),
            decoration: BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.circular(10),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: mostrarAnotada
                  ? Image.memory(
                      _ultimaImagenAnotada!,
                      fit: BoxFit.contain,
                      gaplessPlayback: true,
                    )
                  : (_camaraLista && _camara != null
                      ? Center(
                          child: AspectRatio(
                            aspectRatio: _aspectRatioCamara(),
                            child: CameraPreview(_camara!),
                          ),
                        )
                      : const SizedBox(
                          height: 220,
                          child: Center(
                            child: Text('Inicializando cámara...', style: TextStyle(color: Colors.white70)),
                          ),
                        )),
            ),
          ),

          if (_avisoInferencia != null && _avisoInferencia!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '⚠️ $_avisoInferencia',
              style: TextStyle(fontSize: 11, color: Colors.orange.shade800),
              textAlign: TextAlign.center,
            ),
          ],

          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: (_camaraLista && _casetaId != null) ? _alternarCaptura : null,
            style: FilledButton.styleFrom(
              backgroundColor: _capturando ? Colors.red : Colors.blue,
            ),
            icon: Icon(_capturando ? Icons.stop : Icons.play_arrow),
            label: Text(_capturando ? 'Detener caseta' : 'Iniciar caseta'),
          ),
          const SizedBox(height: 8),
          Text(
            '$_estadoInfo · Frames: $_enviados · ${fpsReales.toStringAsFixed(1)} fps',
            style: const TextStyle(fontSize: 12, color: Colors.black54),
            textAlign: TextAlign.center,
          ),

          // Telemetría en vivo de los modelos (aunque no se haya registrado aún un paso nuevo)
          if (_ultimaDeteccion != null) ...[
            const SizedBox(height: 10),
            Card(
              color: const Color(0xFFF8FAFC),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Detección en tiempo real (M1 · M2 · M3 · Pasajeros)',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Tipo: ${_ultimaDeteccion!['categoria'] ?? '-'} · '
                      'Ejes: ${_ultimaDeteccion!['ejes'] ?? '-'} (ruedas: ${_ultimaDeteccion!['ruedas'] ?? '-'}) · '
                      'Pasajeros: ${_ultimaDeteccion!['pasajeros'] ?? '-'}',
                      style: const TextStyle(fontSize: 12),
                    ),
                    if (_ultimaDeteccion!['latencias'] != null)
                      Text(
                        'Latencias → M1: ${_ultimaDeteccion!['latencias']['m1']}ms · '
                        'M2: ${_ultimaDeteccion!['latencias']['m2']}ms · '
                        'M3: ${_ultimaDeteccion!['latencias']['m3']}ms · '
                        'Pas: ${_ultimaDeteccion!['latencias']['pasajeros']}ms',
                        style: const TextStyle(fontSize: 11, color: Colors.black54),
                      ),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 8),
          if (_ultimoPaso != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          _ultimoPaso!['placa']?.toString() ?? '-',
                          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                        ),
                        Chip(
                          label: Text(
                            _ultimoPaso!['estado']?.toString() ?? '-',
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          ),
                          backgroundColor: _colorEstado(_ultimoPaso!['estado']?.toString()),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text('Categoría: ${_ultimoPaso!['categoria'] ?? '-'} · Ejes: ${_ultimoPaso!['ejes'] ?? '-'}'),
                    Text('Tarifa: Bs ${(_ultimoPaso!['monto'] ?? 0).toString()} · Pasajeros: ${_ultimoPaso!['pasajeros'] ?? '-'}'),
                    Text('Latencia total inferencia: ${_ultimoPaso!['latencia_ms'] ?? '-'} ms'),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
