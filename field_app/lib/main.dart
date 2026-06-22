import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'screens/login_screen.dart';
import 'screens/map_screen.dart';
import 'services/auth_service.dart';
import 'services/team_service.dart';
import 'services/incident_service.dart';
import 'services/route_service.dart';
import 'services/location_service.dart';

void main() {
  runApp(const FieldApp());
}

class FieldApp extends StatelessWidget {
  const FieldApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthService()),
        ChangeNotifierProvider(create: (_) => TeamService()),
        ChangeNotifierProvider(create: (_) => IncidentService()),
        ChangeNotifierProvider(create: (_) => RouteService()),
        ChangeNotifierProxyProvider<AuthService, LocationService>(
          create: (_) => LocationService(AuthService()),
          update: (_, auth, __) => LocationService(auth),
        ),
      ],
      child: MaterialApp(
        title: 'Emergency Field Ops',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          primarySwatch: Colors.blue,
          useMaterial3: true,
        ),
        home: const AppNavigator(),
      ),
    );
  }
}

class AppNavigator extends StatelessWidget {
  const AppNavigator({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = context.watch<AuthService>();
    
    if (authService.isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    
    if (authService.isLoggedIn) {
      return const MapScreen();
    }
    
    return const LoginScreen();
  }
}
