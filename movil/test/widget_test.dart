import 'package:flutter_test/flutter_test.dart';

import 'package:control_peaje/main.dart';

void main() {
  testWidgets('Renderiza ControlPeajeApp', (WidgetTester tester) async {
    await tester.pumpWidget(const ControlPeajeApp());
    expect(find.byType(ControlPeajeApp), findsOneWidget);
  });
}
