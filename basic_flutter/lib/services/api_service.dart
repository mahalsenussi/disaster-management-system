import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class ApiService extends ChangeNotifier {
  // Base URL for the disaster management API
  // Production
  static const String baseUrl = 'https://emergency.onlineacademy.com.ly';
  // Local development: 'http://localhost:5000'
  
  bool _isLoading = false;
  String? _lastError;

  bool get isLoading => _isLoading;
  String? get lastError => _lastError;

  Future<Map<String, dynamic>> get(String endpoint, {String? token}) async {
    try {
      _isLoading = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => notifyListeners());

      final headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };

      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }

      final response = await http.get(
        Uri.parse('$baseUrl$endpoint'),
        headers: headers,
      ).timeout(const Duration(seconds: 30));

      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _lastError = e.toString();
      print('API GET error: $e');
      return {'success': false, 'error': e.toString()};
    } finally {
      _isLoading = false;
      WidgetsBinding.instance.addPostFrameCallback((_) => notifyListeners());
    }
  }

  Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> data, {String? token}) async {
    try {
      _isLoading = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => notifyListeners());

      final headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };

      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }

      final response = await http.post(
        Uri.parse('$baseUrl$endpoint'),
        headers: headers,
        body: json.encode(data),
      ).timeout(const Duration(seconds: 30));

      if (response.statusCode == 200 || response.statusCode == 201) {
        return json.decode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      _lastError = e.toString();
      print('API POST error: $e');
      return {'success': false, 'error': e.toString()};
    } finally {
      _isLoading = false;
      WidgetsBinding.instance.addPostFrameCallback((_) => notifyListeners());
    }
  }

  // Team-specific API methods
  Future<List<dynamic>> getActiveIncidents({String? token}) async {
    final response = await get('/api/incidents', token: token);
    return (response as List<dynamic>?) ?? [];
  }

  Future<Map<String, dynamic>> getTeamAssignments(String teamId, {String? token}) async {
    return await get('/api/team/$teamId/assignments', token: token);
  }

  Future<Map<String, dynamic>> acceptIncident(String teamId, int incidentId, {String? token}) async {
    return await post('/api/team/$teamId/accept-incident', {
      'incident_id': incidentId,
      'accepted_at': DateTime.now().toIso8601String(),
    }, token: token);
  }

  Future<Map<String, dynamic>> getRouteToIncident(String teamId, int incidentId, {String? token}) async {
    return await post('/api/libya-route', {
      'team_id': teamId,
      'incident_id': incidentId,
      'route_type': 'emergency',
    }, token: token);
  }

  Future<Map<String, dynamic>> updateTeamStatus(String teamId, String status, {String? token}) async {
    return await post('/api/team/$teamId/status', {
      'status': status,
      'updated_at': DateTime.now().toIso8601String(),
    }, token: token);
  }

  // V2 GPS Location Update
  Future<Map<String, dynamic>> updateTeamLocationV2({
    required String teamId,
    required double lat,
    required double lng,
    String? token
  }) async {
    try {
      print('V2 GPS sent: team=$teamId lat=$lat lng=$lng');
      
      final response = await post('/api/teams/location', {
        'team_number': int.parse(teamId),
        'lat': lat,
        'lng': lng,
      }, token: token);
      
      return response;
    } catch (e) {
      print('V2 GPS update error: $e');
      return {'success': false, 'error': e.toString()};
    }
  }
}
