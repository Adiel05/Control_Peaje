import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
  bool _mostrarAyudaSha1 = false;
  late final TextEditingController _emailController;

  static const String _sha1App = '75:F5:CD:57:D9:72:77:39:09:C3:2C:9B:F8:23:4A:87:26:15:4D:52';
  static const String _paqueteApp = 'com.controlpeaje.control_peaje';

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

  Future<void> _ingresarGoogle() async {
    setState(() {
      _cargando = true;
      _error = null;
      _mostrarAyudaSha1 = false;
    });

    try {
      final usuario = await AuthService.iniciarSesionGoogle();
      _navegarAInicio(usuario);
    } catch (e) {
      if (!mounted) return;
      final strErr = e.toString();
      setState(() {
        _error = strErr;
        if (strErr.contains('[16]') || strErr.contains('reauth failed') || strErr.contains('SHA-1')) {
          _mostrarAyudaSha1 = true;
        }
      });
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
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
                // Icono e Identidad Visual del Peaje
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.blueAccent.withAlpha(35),
                    border: Border.all(color: Colors.blueAccent.withAlpha(90), width: 2),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.blueAccent.withAlpha(60),
                        blurRadius: 28,
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
                  'Sistema Inteligente de Detección & Cobro Automatizado',
                  style: TextStyle(fontSize: 12, color: Colors.white60),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 14),

                // Badges de los Modelos
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  alignment: WrapAlignment.center,
                  children: [
                    _chipModelo('🔍 M1 Placas OCR', Colors.amber),
                    _chipModelo('🚚 M2 Tipos', Colors.blue),
                    _chipModelo('⚙️ M3 Ejes & Ruedas', Colors.purple),
                    _chipModelo('🛡️ +5 Privacidad', Colors.teal),
                  ],
                ),
                const SizedBox(height: 24),

                // Tarjeta Principal de Inicio de Sesión
                Card(
                  elevation: 8,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  color: const Color(0xFF1E293B),
                  child: Padding(
                    padding: const EdgeInsets.all(22),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          'Acceso al Sistema',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 6),
                        const Text(
                          'Selecciona tu cuenta de Google autorizada para ingresar.',
                          style: TextStyle(color: Colors.white60, fontSize: 13),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),

                        // BOTÓN PRINCIPAL: GOOGLE SIGN-IN OFICIAL
                        ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: const Color(0xFF1F2937),
                            elevation: 3,
                            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          onPressed: _cargando ? null : _ingresarGoogle,
                          child: _cargando
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2.2, color: Colors.blueAccent),
                                )
                              : Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    _iconoGoogle(),
                                    const SizedBox(width: 12),
                                    const Text(
                                      'Ingresar con Google',
                                      style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                        letterSpacing: 0.2,
                                      ),
                                    ),
                                  ],
                                ),
                        ),

                        // Alerta si ocurre el error [16] de Google Play Services
                        if (_mostrarAyudaSha1) ...[
                          const SizedBox(height: 16),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.amber.shade900.withAlpha(60),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: Colors.amber.shade400),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Row(
                                  children: [
                                    Icon(Icons.info_outline, color: Colors.amberAccent, size: 20),
                                    SizedBox(width: 8),
                                    Text(
                                      'Vincular SHA-1 en Google Cloud',
                                      style: TextStyle(
                                        color: Colors.amberAccent,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                const Text(
                                  'Para que Google muestre tus cuentas en el celular, registra esta app en Google Cloud (Credenciales → Crear OAuth Android):',
                                  style: TextStyle(color: Colors.white70, fontSize: 11),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  '• Paquete: $_paqueteApp\n• SHA-1: $_sha1App',
                                  style: const TextStyle(
                                    color: Colors.cyanAccent,
                                    fontSize: 11,
                                    fontFamily: 'monospace',
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: TextButton.icon(
                                    onPressed: () {
                                      Clipboard.setData(const ClipboardData(text: _sha1App));
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        const SnackBar(content: Text('SHA-1 copiado al portapapeles')),
                                      );
                                    },
                                    icon: const Icon(Icons.copy, size: 14, color: Colors.amberAccent),
                                    label: const Text(
                                      'Copiar SHA-1',
                                      style: TextStyle(color: Colors.amberAccent, fontSize: 11),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],

                        // Otros mensajes de error
                        if (_error != null && !_mostrarAyudaSha1) ...[
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

                        const SizedBox(height: 20),
                        Row(
                          children: [
                            const Expanded(child: Divider(color: Colors.white24)),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 10),
                              child: Text(
                                'o acceso de emergencia',
                                style: TextStyle(color: Colors.white38, fontSize: 11),
                              ),
                            ),
                            const Expanded(child: Divider(color: Colors.white24)),
                          ],
                        ),
                        const SizedBox(height: 14),

                        // Acceso rápido directo como respaldo
                        OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white70,
                            side: const BorderSide(color: Colors.white24),
                            padding: const EdgeInsets.symmetric(vertical: 11),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          ),
                          onPressed: _cargando ? null : _ingresarDirecto,
                          icon: const Icon(Icons.flash_on, color: Colors.amberAccent, size: 18),
                          label: Text(
                            'Entrar directo como ${_emailController.text}',
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
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

  Widget _iconoGoogle() {
    return SizedBox(
      width: 22,
      height: 22,
      child: CustomPaint(
        painter: _GoogleLogoPainter(),
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

class _GoogleLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final double w = size.width;
    final double h = size.height;

    final paintBlue = Paint()..color = const Color(0xFF4285F4);
    final paintRed = Paint()..color = const Color(0xFFEA4335);
    final paintYellow = Paint()..color = const Color(0xFFFBBC05);
    final paintGreen = Paint()..color = const Color(0xFF34A853);

    final center = Offset(w / 2, h / 2);
    final radius = w / 2;

    // Barra horizontal derecha
    canvas.drawRect(
      Rect.fromLTRB(w * 0.45, h * 0.4, w, h * 0.6),
      paintBlue,
    );

    // Arcos circulares
    final rect = Rect.fromCircle(center: center, radius: radius);
    canvas.drawArc(rect, -0.6, 1.2, false, paintBlue..style = PaintingStyle.stroke..strokeWidth = w * 0.22);
    canvas.drawArc(rect, 0.6, 1.5, false, paintGreen..style = PaintingStyle.stroke..strokeWidth = w * 0.22);
    canvas.drawArc(rect, 2.1, 1.3, false, paintYellow..style = PaintingStyle.stroke..strokeWidth = w * 0.22);
    canvas.drawArc(rect, 3.4, 1.3, false, paintRed..style = PaintingStyle.stroke..strokeWidth = w * 0.22);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
