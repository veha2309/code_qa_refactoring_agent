import 'package:flutter/material.dart';

class AuthCard extends StatelessWidget {
  const AuthCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const Card(child: Padding(
      padding: EdgeInsets.all(24),
      child: Text('Welcome to Change Lens'),
    ));
  }
}
