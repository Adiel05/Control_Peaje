import 'package:flutter/material.dart';

import '../config.dart';
import '../servicios/api.dart';
import '../servicios/auth.dart';
import 'inicio.dart';

class LoginPantalla extends StatefulWidget {
  const LoginPantalla({super.key});

  @override
  State<LoginPantalla> createState() => _LoginPantallaState();
}

class _LoginPantallaState extends State<LoginPantalla> {
  bool _cargando = false;
  String? _error;
  late final TextEditingController _emailController;
  bool _editandoEmail = false;

  @override
  void initState() {
    super.initState();
    _emailController = TextEditingController(text: AuthService.emailAdminDefault);
    _cargarUltimoEmail();
  }

  Future<void> _cargarUltimoEmail() async {
    final guardado = await AuthService.obtenerUltimoEmailAdmin();
    if (mounted && guardado.isNotEmpty) {
      setState(() {
        _emailController.text = guardado;
      });
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  void _navegarAInicio(Map<String, dynamic> usuario) {
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => InicioPantalla(usuario: usuario)),
    );
  }

  Future<void> _ingresarDirecto() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      setState(() => _error = 'Por favor ingresa un correo de administrador');
      return;
    }

    setState(() {
      _cargando = true;
      _error = null;
    });

    try {
      final usuario = await AuthService.iniciarSesionDirecta(email);
      _navegarAInicio(usuario);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _ingresarGoogle() async {
    setState(() {
      _cargando = true;
      _error = null;
    });

    try {
      final usuario = await AuthService.iniciarSesionGoogle();
      _navegarAInicio(usuario);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  void _abrirAjustesServidor() async {
    final controller = TextEditingController(text: await AppConfig.getApiBase());
    String? estadoPing;
    bool probando = false;

    if (!mounted) return;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.settings, color: Colors.blueAccent),
              SizedBox(width: 8),
              Text('Servidor Backend', style: TextStyle(fontSize: 18)),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'URL del backend FastAPI en Render o red local:',
                style: TextStyle(fontSize: 13, color: Colors.black54),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  hintText: 'https://peaje-web.onrender.com',
                  isDense: true,
                ),
              ),
              const SizedBox(height: 12),
              if (estadoPing != null)
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: estadoPing!.startsWith('✅') ? Colors.green.shade50 : Colors.red.shade50,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: estadoPing!.startsWith('✅') ? Colors.green.shade200 : Colors.red.shade200,
                    ),
                  ),
                  child: Text(estadoPing!, style: const TextStyle(fontSize: 12)),
                ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: probando
                      ? null
                      : () async {
                          setDialogState(() {
                            probando = true;
                            estadoPing = 'Conectando con ${controller.text}...';
                          });
                          try {
                            final res = await ApiService.probarConexion(controller.text);
                            setDialogState(() {
                              probando = false;
                              estadoPing = '✅ Conexión exitosa (${res['latencia_ms']} ms)';
                            });
                          } catch (err) {
                            setDialogState(() {
                              probando = false;
                              estadoPing = '❌ Sin respuesta: $err';
                            });
                          }
                        },
                  icon: probando
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.wifi_tethering, size: 16),
                  label: const Text('Probar Conexión'),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () async {
                await AppConfig.setApiBase(controller.text);
                if (ctx.mounted) Navigator.pop(ctx);
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('URL del servidor actualizada')),
                  );
                }
              },
              child: const Text('Guardar'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: Colors.white70),
            tooltip: 'Configurar servidor',
            onPressed: _abrirAjustesServidor,
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Cabecera con ilustración y logo del sistema
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.blueAccent.withAlpha(35),
                    border: Border.all(color: Colors.blueAccent.withAlpha(90), width: 2),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.blueAccent.withAlpha(50),
                        blurRadius: 24,
                        spreadRadius: 4,
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.toll_rounded,
                    size: 64,
                    color: Colors.cyanAccent,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Control de Peaje IA',
                  style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Gestión Automatizada & Visión por Computadora',
                  style: TextStyle(fontSize: 13, color: Colors.white60),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 14),

                // Badges de modelos de IA
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  alignment: WrapAlignment.center,
                  children: [
                    _chipModelo('🔍 M1 Placas', Colors.amber),
                    _chipModelo('🚚 M2 Tipos', Colors.blue),
                    _chipModelo('⚙️ M3 Ejes', Colors.purple),
                    _chipModelo('🛡️ +5 Privacidad', Colors.teal),
                  ],
                ),
                const SizedBox(height: 24),

                // Tarjeta Principal de Inicio de Sesión
                Card(
                  elevation: 6,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  color: const Color(0xFF1E293B),
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Sección de Acceso Directo de Administrador
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: Colors.blueGrey.shade800),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  const Icon(Icons.verified_user, color: Colors.greenAccent, size: 18),
                                  const SizedBox(width: 6),
                                  const Text(
                                    'Acceso Administrador Autorizado',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w600,
                                      fontSize: 13,
                                    ),
                                  ),
                                  const Spacer(),
                                  IconButton(
                                    icon: Icon(
                                      _editandoEmail ? Icons.check : Icons.edit,
                                      color: Colors.white70,
                                      size: 16,
                                    ),
                                    onPressed: () {
                                      setState(() => _editandoEmail = !_editandoEmail);
                                    },
                                    tooltip: _editandoEmail ? 'Listo' : 'Cambiar correo',
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              if (_editandoEmail)
                                TextField(
                                  controller: _emailController,
                                  style: const TextStyle(color: Colors.white, fontSize: 13),
                                  decoration: InputDecoration(
                                    isDense: true,
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                    filled: true,
                                    fillColor: const Color(0xFF1E293B),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(6),
                                      borderSide: BorderSide(color: Colors.blueAccent.shade100),
                                    ),
                                  ),
                                )
                              else
                                Text(
                                  _emailController.text,
                                  style: const TextStyle(
                                    color: Colors.cyanAccent,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Botón de Acceso Directo
                        FilledButton.icon(
                          style: FilledButton.styleFrom(
                            backgroundColor: Colors.blueAccent,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          onPressed: _cargando ? null : _ingresarDirecto,
                          icon: _cargando
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : const Icon(Icons.login_rounded),
                          label: Text(
                            _cargando ? 'Iniciando sesión...' : 'Entrar como Administrador',
                            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                          ),
                        ),

                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(child: Divider(color: Colors.white24)),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 10),
                              child: Text('o ingresar con cuenta', style: TextStyle(color: Colors.white38, fontSize: 11)),
                            ),
                            Expanded(child: Divider(color: Colors.white24)),
                          ],
                        ),
                        const SizedBox(height: 14),

                        // Botón de Google Sign-In
                        OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: const BorderSide(color: Colors.white30),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          onPressed: _cargando ? null : _ingresarGoogle,
                          icon: const Icon(Icons.account_circle, color: Colors.white70),
                          label: const Text('Google Sign-In'),
                        ),

                        // Alerta de Error
                        if (_error != null) ...[
                          const SizedBox(height: 16),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.red.shade900.withAlpha(80),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: Colors.redAccent.shade100),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.error_outline, color: Colors.redAccent, size: 20),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _error!,
                                    style: const TextStyle(color: Colors.white, fontSize: 12),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 20),
                const Text(
                  'Universidad Franz Tamayo · Inteligencia Artificial\nAutor: Noel Pabón Nina (Adiel)',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white38, fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _chipModelo(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withAlpha(120), width: 1),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w600),
      ),
    );
  }
}
