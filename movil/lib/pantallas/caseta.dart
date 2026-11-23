import 'dart:async';

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
      final ctrl = CameraController(trasera, ResolutionPreset.high, enableAudio: false);
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

    _timer = Timer.periodic(const Duration(milliseconds: 400), (_) => _tickFrame());
  }

  Future<void> _tickFrame() async {
    if (!_capturando || _camara == null || !_camara!.value.isInitialized) return;
    if (_enVuelo >= 2 || _camara!.value.isTakingPicture) return;
    final caseta = _casetaId;
    if (caseta == null) return;

    _enVuelo++;
    try {
      final xfile = await _camara!.takePicture();
      final bytes = await xfile.readAsBytes();
      final resp = await ApiService.enviarFrame(bytes, caseta);
      if (!mounted) return;
      _enviados++;
      setState(() {
        if (resp['registrado'] == true) {
          _ultimoPaso = resp;
          _estadoInfo = 'Registrado: ${resp['placa']} (${resp['estado']})';
        } else {
          _estadoInfo = 'Ignorado: ${resp['motivo'] ?? 'sin cambios'}';
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
          AspectRatio(
            aspectRatio: 16 / 9,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: _camaraLista && _camara != null
                  ? CameraPreview(_camara!)
                  : const ColoredBox(
                      color: Colors.black12,
                      child: Center(child: Text('Inicializando cámara...')),
                    ),
            ),
          ),
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
          const SizedBox(height: 12),
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
