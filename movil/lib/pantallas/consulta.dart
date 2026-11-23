import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../servicios/api.dart';

class _MensajeChat {
  final bool esUsuario;
  final String texto;
  final List<String> sugerencias;
  _MensajeChat({required this.esUsuario, required this.texto, this.sugerencias = const []});
}

class ConsultaPantalla extends StatefulWidget {
  final VoidCallback onSesionExpirada;
  const ConsultaPantalla({super.key, required this.onSesionExpirada});

  @override
  State<ConsultaPantalla> createState() => _ConsultaPantallaState();
}

class _ConsultaPantallaState extends State<ConsultaPantalla> {
  final _ctrl = TextEditingController();
  final _picker = ImagePicker();
  final List<_MensajeChat> _mensajes = [
    _MensajeChat(
      esUsuario: false,
      texto: 'Consulta cualquier placa por texto (ej. 1234ABC) o envía una foto.',
    ),
  ];
  final List<Map<String, String>> _historial = [];
  bool _enviando = false;

  Future<void> _enviar({String? texto, Uint8List? imagenBytes}) async {
    final msg = (texto ?? _ctrl.text).trim();
    if (msg.isEmpty && imagenBytes == null) return;
    if (texto == null) _ctrl.clear();

    final etiqueta = msg.isNotEmpty ? msg : '[Foto enviada]';
    setState(() {
      _enviando = true;
      _mensajes.add(_MensajeChat(esUsuario: true, texto: etiqueta));
    });

    try {
      final resp = await ApiService.chat(
        mensaje: msg.isNotEmpty ? msg : null,
        imagenBytes: imagenBytes,
        historial: _historial.length > 6 ? _historial.sublist(_historial.length - 6) : _historial,
      );
      final respuesta = resp['respuesta']?.toString() ?? 'Sin respuesta';
      final sugs = (resp['sugerencias'] as List<dynamic>? ?? []).map((e) => e.toString()).toList();
      _historial.add({'rol': 'usuario', 'texto': etiqueta});
      _historial.add({'rol': 'asistente', 'texto': respuesta});
      if (!mounted) return;
      setState(() {
        _mensajes.add(_MensajeChat(esUsuario: false, texto: respuesta, sugerencias: sugs));
      });
    } on SesionExpiradaException {
      widget.onSesionExpirada();
    } catch (e) {
      if (mounted) {
        setState(() {
          _mensajes.add(_MensajeChat(esUsuario: false, texto: 'Error: $e'));
        });
      }
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  Future<void> _elegirFoto(ImageSource fuente) async {
    final foto = await _picker.pickImage(source: fuente, maxWidth: 1280, imageQuality: 85);
    if (foto == null) return;
    final bytes = await foto.readAsBytes();
    await _enviar(imagenBytes: bytes);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: _mensajes.length,
            itemBuilder: (_, i) {
              final m = _mensajes[i];
              return Align(
                alignment: m.esUsuario ? Alignment.centerRight : Alignment.centerLeft,
                child: Container(
                  margin: const EdgeInsets.symmetric(vertical: 4),
                  padding: const EdgeInsets.all(12),
                  constraints: const BoxConstraints(maxWidth: 320),
                  decoration: BoxDecoration(
                    color: m.esUsuario ? Colors.blue.shade700 : Colors.grey.shade200,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        m.texto,
                        style: TextStyle(color: m.esUsuario ? Colors.white : Colors.black87),
                      ),
                      if (m.sugerencias.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 6,
                          children: m.sugerencias
                              .map((s) => ActionChip(
                                    label: Text('¿Quisiste decir $s?'),
                                    onPressed: _enviando ? null : () => _enviar(texto: 'Consultar $s'),
                                  ))
                              .toList(),
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Tomar foto',
                icon: const Icon(Icons.camera_alt),
                onPressed: _enviando ? null : () => _elegirFoto(ImageSource.camera),
              ),
              IconButton(
                tooltip: 'Elegir de galería',
                icon: const Icon(Icons.photo_library),
                onPressed: _enviando ? null : () => _elegirFoto(ImageSource.gallery),
              ),
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  decoration: const InputDecoration(
                    hintText: 'Placa o pregunta...',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  onSubmitted: (_) => _enviar(),
                ),
              ),
              const SizedBox(width: 6),
              IconButton.filled(
                icon: _enviando
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.send),
                onPressed: _enviando ? null : () => _enviar(),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
