import 'dart:convert';
import 'package:latlong2/latlong.dart';
import 'api_service.dart';

class RouteService {
  final ApiService _apiService;
  
  RouteService(this._apiService);
  
  // Check for assigned routes for the current team
  Future<Map<String, dynamic>?> getAssignedRoute(int teamId) async {
    try {
      final response = await _apiService.get('/api/team/$teamId/assigned-route');
      
      if (response['success'] == true && response['route'] != null) {
        return response['route'];
      }
      
      return null;
    } catch (e) {
      print('Error getting assigned route: $e');
      return null;
    }
  }
  
  // Get assigned route from new endpoint
  Future<Map<String, dynamic>?> getAssignedRouteV2(String teamId) async {
    try {
      print("Fetching route for team: $teamId");
      final response = await _apiService.get('/api/teams/$teamId/route');
      print("Route response: $response");
      
      if (response['active'] == true) {
        return response;
      }
      
      return null;
    } catch (e) {
      print('Error getting assigned route v2: $e');
      return null;
    }
  }
  
  // Parse route data and convert to LatLng points
  List<LatLng> parseRouteData(String routeData) {
    try {
      final Map<String, dynamic> routeMap = json.decode(routeData);
      
      if (routeMap['geometry'] != null && routeMap['geometry']['coordinates'] != null) {
        final List<dynamic> coordinates = routeMap['geometry']['coordinates'];
        return coordinates.map((coord) => LatLng(coord[1], coord[0])).toList();
      }
      
      return [];
    } catch (e) {
      print('Error parsing route data: $e');
      return [];
    }
  }
  
  // Calculate distance between two points
  double calculateDistance(LatLng start, LatLng end) {
    const Distance distance = Distance();
    return distance.as(LengthUnit.Kilometer, start, end);
  }
  
  // Calculate estimated duration (simplified calculation)
  Duration calculateDuration(double distance, String routeType) {
    double speedKmh;
    
    switch (routeType) {
      case 'walking':
        speedKmh = 5.0; // Average walking speed
        break;
      case 'emergency':
        speedKmh = 80.0; // Emergency vehicle speed
        break;
      case 'driving':
      default:
        speedKmh = 60.0; // Average driving speed
        break;
    }
    
    final double hours = distance / speedKmh;
    return Duration(minutes: (hours * 60).round());
  }
}
