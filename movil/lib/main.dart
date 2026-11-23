import 'package:flutter/material.dart';

import 'pantallas/inicio.dart';
import 'pantallas/login.dart';
import 'servicios/auth.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ControlPeajeApp());
}

class ControlPeajeApp extends StatelessWidget {
  const ControlPeajeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Control Peaje',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: const _Arranque(),
    );
  }
}

class _Arranque extends StatefulWidget {
  const _Arranque();

  @override
  State<_Arranque> createState() => _ArranqueState();
}

class _ArranqueState extends State<_Arranque> {
  late final Future<Map<String, dynamic>?> _sesion = _cargar();

  Future<Map<String, dynamic>?> _cargar() async {
    final token = await AuthService.obtenerToken();
    final usuario = await AuthService.obtenerUsuario();
    if (token != null && token.isNotEmpty && usuario != null) {
      return usuario;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: _sesion,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        final usuario = snap.data;
        if (usuario != null) {
          return InicioPantalla(usuario: usuario);
        }
        return const LoginPantalla();
      },
    );
  }
}
