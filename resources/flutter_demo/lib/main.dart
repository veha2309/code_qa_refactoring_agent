import 'package:flutter/material.dart';
import 'screens.dart';

void main() => runApp(const DemoApp());

class DemoApp extends StatelessWidget {
  const DemoApp({super.key, this.register = false});
  final bool register;

  @override
  Widget build(BuildContext context) => MaterialApp(
    home: register ? const RegisterScreen() : const LoginScreen(),
  );
}
