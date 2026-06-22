import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../services/location_service.dart';
import '../services/auth_service.dart';
import '../services/route_service.dart';
import '../services/api_service.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _mapController = MapController();
  List<LatLng> routePoints = [];
  Map<String, dynamic>? activeRoute;
  LatLng? _destination;
  LatLng _currentCenter = const LatLng(32.8872, 13.1913); // Default to Tripoli
  double _currentZoom = 13.0;
  
  // Route service for assigned routes
  late RouteService _routeService;
  Timer? _routeCheckTimer;

  @override
  void initState() {
    super.initState();
    final apiService = Provider.of<ApiService>(context, listen: false);
    _routeService = RouteService(apiService);
    
    // Start checking for assigned routes every 10 seconds
    _routeCheckTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _checkForAssignedRoute();
    });
    
    // Check immediately on init
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkForAssignedRoute();
    });
  }
  
  @override
  void dispose() {
    _routeCheckTimer?.cancel();
    super.dispose();
  }
  
  void updateRoute(Map<String, dynamic> routeData) {
    final path = routeData['route']['path'];
    
    routePoints = path.map<LatLng>((p) {
      return LatLng(p[0], p[1]);
    }).toList();
    
    activeRoute = routeData;
    
    print("Route updated: ${routePoints.length} points");
    
    setState(() {});
  }
  
  Future<void> _checkForAssignedRoute() async {
    final authService = Provider.of<AuthService>(context, listen: false);
    final teamId = authService.teamId;
    
    if (teamId != null) {
      try {
        final assignedRoute = await _routeService.getAssignedRouteV2(teamId);
        
        if (assignedRoute != null) {
          print("Route found, updating...");
          updateRoute(assignedRoute);
          
          // Center map on route start
          if (routePoints.isNotEmpty) {
            _mapController.move(routePoints.first, 14.0);
          }
        } else {
          print("No active route found");
        }
      } catch (e) {
        print("Error checking for route: $e");
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final locationService = Provider.of<LocationService>(context);
    final currentPosition = locationService.currentPosition;

    return Scaffold(
      appBar: AppBar(
        title: const Text('خريطة الفريق'),
        backgroundColor: Colors.blue.shade800,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.my_location),
            onPressed: () {
              if (currentPosition != null) {
                _mapController.move(
                  LatLng(currentPosition.latitude, currentPosition.longitude),
                  15.0,
                );
              }
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: currentPosition != null
                  ? LatLng(currentPosition.latitude, currentPosition.longitude)
                  : const LatLng(32.8872, 13.1913), // Default to Tripoli
              initialZoom: 13.0,
              onPositionChanged: (position, hasGesture) {
                if (hasGesture) {
                  setState(() {
                    _currentCenter = position.center ?? _currentCenter;
                    _currentZoom = position.zoom ?? _currentZoom;
                  });
                }
              },
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=udTzwXECIT3ySQhmBDs4',
                subdomains: const ['a', 'b', 'c', 'd'],
                maxZoom: 19,
                retinaMode: false,
                tileProvider: NetworkTileProvider(),
              ),
              // Current location marker
              if (currentPosition != null)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: LatLng(currentPosition.latitude, currentPosition.longitude),
                      width: 40,
                      height: 40,
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.blue.shade800,
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 3),
                        ),
                        child: const Icon(
                          Icons.local_shipping,
                          color: Colors.white,
                          size: 20,
                        ),
                      ),
                    ),
                  ],
                ),
              // Route polyline
              if (routePoints.isNotEmpty)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: routePoints,
                      strokeWidth: 5.0,
                      color: Colors.red,
                    ),
                  ],
                ),
              // Destination marker (incident)
              if (routePoints.isNotEmpty)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: routePoints.last,
                      width: 40,
                      height: 40,
                      child: const Icon(Icons.warning, color: Colors.red),
                    ),
                  ],
                ),
            ],
          ),
          // Info panel overlay
          if (activeRoute != null && routePoints.isNotEmpty)
            Positioned(
              top: 60,
              left: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.2),
                      blurRadius: 10,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Row(
                  children: [
                    const Icon(Icons.warning, color: Colors.red, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _getRouteInfoText(),
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
      floatingActionButton: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          FloatingActionButton(
            heroTag: 'zoomIn',
            mini: true,
            onPressed: () {
              _mapController.move(_currentCenter, _currentZoom + 1);
            },
            child: const Icon(Icons.add),
          ),
          const SizedBox(height: 8),
          FloatingActionButton(
            heroTag: 'zoomOut',
            mini: true,
            onPressed: () {
              _mapController.move(_currentCenter, _currentZoom - 1);
            },
            child: const Icon(Icons.remove),
          ),
        ],
      ),
    );
  }

  void setRoute(List<LatLng> routePoints, LatLng destination) {
    setState(() {
      this.routePoints = routePoints;
      _destination = destination;
    });

    // Center map on first route point (simplified fit bounds)
    if (routePoints.isNotEmpty) {
      _mapController.move(routePoints.first, 15.0);
    }
  }
  
  String _getRouteInfoText() {
    if (activeRoute == null) return '';
    
    final incident = activeRoute!['incident'];
    final route = activeRoute!['route'];
    
    final type = incident['type'] ?? 'Unknown';
    final distance = (route['distance'] ?? 0).toStringAsFixed(1);
    final duration = (route['duration'] ?? 0) / 60; // Convert to minutes
    
    return '🚨 $type | ${duration.round()} min | $distance km';
  }
}
