import 'package:flutter_test/flutter_test.dart';
import 'package:change_lens_flutter_demo/main.dart';

void main() {
  testWidgets('login includes shared auth card', (tester) async {
    await tester.pumpWidget(const DemoApp());
    expect(find.text('Welcome to Change Lens'), findsOneWidget);
  });
  testWidgets('register includes shared auth card', (tester) async {
    await tester.pumpWidget(const DemoApp(register: true));
    expect(find.text('Welcome to Change Lens'), findsOneWidget);
  });
}
