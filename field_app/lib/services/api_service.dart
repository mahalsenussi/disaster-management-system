import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  // Production server URL (HTTPS to avoid 301 redirect)
  static const String baseUrl = 'https://emergency.onlineacademy.com.ly';
  
  /// Get JWT token from SharedPreferences
  static Future<String?> _getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('auth_token');
  }
  
  /// Build headers with optional auth token
  static Future<Map<String, String>> _buildHeaders({bool requireAuth = false}) async {
    final headers = {'Content-Type': 'application/json'};
    
    if (requireAuth) {
      final token = await _getToken();
      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      }
    }
    
    return headers;
  }
  
  static Future<dynamic> get(String endpoint, {bool requireAuth = false}) async {
    try {
      final headers = await _buildHeaders(requireAuth: requireAuth);
      final response = await http.get(
        Uri.parse('$baseUrl$endpoint'),
        headers: headers,
      ).timeout(const Duration(seconds: 10)).then((response) {
        // Follow redirects manually if needed
        if (response.statusCode == 301 || response.statusCode == 302) {
          final location = response.headers['location'];
          if (location != null) {
            return http.get(
              Uri.parse(location),
              headers: headers,
            ).timeout(const Duration(seconds: 10));
          }
        }
        return Future.value(response);
      });
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}');
      }
    } catch (e) {
      print('API GET Error [$endpoint]: $e');
      rethrow;
    }
  }
  
  static Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> data, {bool requireAuth = false}) async {
    try {
      final headers = await _buildHeaders(requireAuth: requireAuth);
      final response = await http.post(
        Uri.parse('$baseUrl$endpoint'),
        headers: headers,
        body: json.encode(data),
      ).timeout(const Duration(seconds: 10)).then((response) {
        // Follow redirects manually if needed
        if (response.statusCode == 301 || response.statusCode == 302) {
          final location = response.headers['location'];
          if (location != null) {
            return http.post(
              Uri.parse(location),
              headers: headers,
              body: json.encode(data),
            ).timeout(const Duration(seconds: 10));
          }
        }
        return Future.value(response);
      });
      
      if (response.statusCode == 200 || response.statusCode == 201) {
        return json.decode(response.body);
      } else {
        throw Exception('HTTP ${response.statusCode}');
      }
    } catch (e) {
      print('API POST Error [$endpoint]: $e');
      rethrow;
    }
  }
  
  static bool get isOnline => true; // Simplified for now
  
  /// Get branches for login (no auth required)
  static Future<List<Map<String, dynamic>>> getBranches() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/api/branches/public'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));
      
      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        return data.cast<Map<String, dynamic>>();
      } else {
        throw Exception('HTTP ${response.statusCode}');
      }
    } catch (e) {
      print('API GET Branches Error: $e');
      rethrow;
    }
  }
}
