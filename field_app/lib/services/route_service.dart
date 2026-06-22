import 'dart:async';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'api_service.dart';

class RouteData {
  final bool active;
  final Incident incident;
  final RouteInfo route;
  
  RouteData({
    required this.active,
    required this.incident,
    required this.route,
  });
  
  factory RouteData.fromJson(Map<String, dynamic> json) {
    return RouteData(
      active: json['active'] ?? false,
      incident: Incident.fromJson(json['incident']),
      route: RouteInfo.fromJson(json['route']),
    );
  }
}

class Incident {
  final int id;
  final String type;
  final String severity;
  final String status;
  final double lat;
  final double lng;
  
  Incident({
    required this.id,
    required this.type,
    required this.severity,
    required this.status,
    required this.lat,
    required this.lng,
  });
  
  factory Incident.fromJson(Map<String, dynamic> json) {
    return Incident(
      id: json['id'],
      type: json['type'] ?? '',
      severity: json['severity'] ?? 'medium',
      status: json['status'] ?? 'open',
      lat: (json['lat'] ?? 0.0).toDouble(),
      lng: (json['lng'] ?? 0.0).toDouble(),
    );
  }
}

class RouteInfo {
  final int id;
  final List<List<double>> path;
  final double distance;
  final double duration;
  
  RouteInfo({
    required this.id,
    required this.path,
    required this.distance,
    required this.duration,
  });
  
  factory RouteInfo.fromJson(Map<String, dynamic> json) {
    final pathList = json['path'] as List? ?? [];
    // Server already returns [lat, lng]
    final path = pathList.map((p) => [p[0] as double, p[1] as double]).toList();
    
    return RouteInfo(
      id: json['id'] ?? 0,
      path: path,
      distance: (json['distance'] ?? 0.0).toDouble(),
      duration: (json['duration'] ?? 0.0).toDouble(),
    );
  }
}

class RouteService with ChangeNotifier {
  RouteData? _currentRoute;
  bool _isLoading = false;
  bool _isRerouting = false;
  DateTime? _lastRerouteTime;
  Timer? _refreshTimer;
  
  // Rerouting threshold: 80 meters
  static const double _rerouteThresholdMeters = 80.0;
  // Cooldown: 20 seconds
  static const Duration _rerouteCooldown = Duration(seconds: 20);
  
  RouteData? get currentRoute => _currentRoute;
  bool get isLoading => _isLoading;
  bool get isRerouting => _isRerouting;
  
  void startAutoRefresh(int teamId) {
    fetchRoute(teamId);
    _refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      fetchRoute(teamId);
    });
  }
  
  void stopAutoRefresh() {
    _refreshTimer?.cancel();
  }
  
  @override
  void dispose() {
    stopAutoRefresh();
    super.dispose();
  }
  
  Future<void> fetchRoute(int teamId) async {
    if (_isLoading) return;
    
    _isLoading = true;
    notifyListeners();
    
    try {
      final response = await ApiService.get('/api/teams/$teamId/route');
      
      if (response['active'] == true) {
        final newRoute = RouteData.fromJson(response);
        
        // Only update if route changed
        if (_currentRoute == null || 
            _currentRoute!.route.id != newRoute.route.id) {
          _currentRoute = newRoute;
          print('Route updated: ${newRoute.route.id}');
        }
      } else {
        _currentRoute = null;
      }
    } catch (e) {
      print('Fetch route error: $e');
      // Keep last route on error
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
  
  // Check if user deviated from route
  bool checkDeviation(LatLng currentLocation) {
    if (_currentRoute == null || _currentRoute!.route.path.isEmpty) {
      return false;
    }
    
    final path = _currentRoute!.route.path;
    double minDistance = double.infinity;
    
    for (final point in path) {
      final routePoint = LatLng(point[0], point[1]);
      final distance = Geolocator.distanceBetween(
        currentLocation.latitude,
        currentLocation.longitude,
        routePoint.latitude,
        routePoint.longitude,
      );
      
      if (distance < minDistance) {
        minDistance = distance;
      }
    }
    
    print('Distance to route: ${minDistance.toStringAsFixed(1)}m');
    return minDistance > _rerouteThresholdMeters;
  }
  
  // Trigger reroute
  Future<bool> reroute(int teamId, LatLng currentLocation) async {
    // Reroute endpoint not available on server
    print('Reroute endpoint not available - skipping');
    return false;
  }
}

// Geolocator helper for distance calculation
class Geolocator {
  static double distanceBetween(double lat1, double lng1, double lat2, double lng2) {
    const Distance distance = Distance();
    return distance.as(LengthUnit.Meter, LatLng(lat1, lng1), LatLng(lat2, lng2));
  }
}
