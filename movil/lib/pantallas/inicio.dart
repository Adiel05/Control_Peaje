import 'package:flutter/material.dart';

import '../servicios/auth.dart';
import 'caseta.dart';
import 'consulta.dart';
import 'login.dart';

class InicioPantalla extends StatefulWidget {
  final Map<String, dynamic> usuario;
  const InicioPantalla({super.key, required this.usuario});

  @override
  State<InicioPantalla> createState() => _InicioPantallaState();
}

class _InicioPantallaState extends State<InicioPantalla> {
  int _indice = 0;

  Future<void> _salir() async {
    await AuthService.cerrarSesion();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginPantalla()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final paginas = [
      CasetaPantalla(onSesionExpirada: _salir),
      ConsultaPantalla(onSesionExpirada: _salir),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(_indice == 0 ? 'Modo Caseta' : 'Modo Consulta'),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Center(
              child: Text(
                widget.usuario['rol']?.toString() ?? '',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout),
            onPressed: _salir,
          ),
        ],
      ),
      body: IndexedStack(index: _indice, children: paginas),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _indice,
        onDestinationSelected: (i) => setState(() => _indice = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.videocam), label: 'Caseta'),
          NavigationDestination(icon: Icon(Icons.chat), label: 'Consulta'),
        ],
      ),
    );
  }
}
