import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';

class AuthService with ChangeNotifier {
  String? _teamId;
  String? _teamNumber;
  String? _teamName;
  int? _branchId;
  String? _token;  // JWT token
  bool _isLoading = true;
  bool _isLoggedIn = false;
  
  String? get teamId => _teamId;
  String? get teamNumber => _teamNumber;
  String? get teamName => _teamName;
  int? get branchId => _branchId;
  String? get token => _token;
  bool get isLoading => _isLoading;
  bool get isLoggedIn => _isLoggedIn;
  
  AuthService() {
    _checkLoginStatus();
  }
  
  Future<void> _checkLoginStatus() async {
    _isLoading = true;
    notifyListeners();
    
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedTeamId = prefs.getString('team_id');
      final savedTeamNumber = prefs.getString('team_number');
      final savedTeamName = prefs.getString('team_name');
      final savedBranchId = prefs.getInt('branch_id');
      final savedToken = prefs.getString('auth_token');
      
      // Check if token exists and is valid (not expired)
      if (savedToken != null && savedTeamId != null) {
        // TODO: Optionally validate token with server
        _teamId = savedTeamId;
        _teamNumber = savedTeamNumber;
        _teamName = savedTeamName;
        _branchId = savedBranchId;
        _token = savedToken;
        _isLoggedIn = true;
        print('Auto-login: Team $_teamNumber (Branch: $_branchId)');
      }
    } catch (e) {
      print('Auto-login error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
  
  /// Login with team number and branch ID
  /// NEW: Uses JWT token-based auth with branch isolation
  Future<bool> loginWithTeamNumber(String teamNumber, int branchId) async {
    try {
      // NEW: Call mobile login endpoint with team_number + branch_id
      final response = await ApiService.post('/api/mobile/login', {
        'team_number': teamNumber,
        'branch_id': branchId,
      });
      
      if (response['token'] == null) {
        print('Login failed: No token received');
        return false;
      }
      
      _token = response['token'];
      _teamId = response['team_id'].toString();
      _teamNumber = response['team_number']?.toString();
      _teamName = response['team_name'];
      _branchId = response['branch_id'];
      _isLoggedIn = true;
      
      // Store token and credentials for offline use
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_token', _token!);
      await prefs.setString('team_id', _teamId!);
      await prefs.setString('team_number', _teamNumber!);
      await prefs.setString('team_name', _teamName!);
      await prefs.setInt('branch_id', _branchId!);
      
      print('Login successful: Team $_teamNumber (Branch: $_branchId)');
      print('Token expires in: ${response['expires_in'] ?? '7 days'} seconds');
      notifyListeners();
      return true;
    } catch (e) {
      print('Login error: $e');
      return false;
    }
  }
  
  /// Login with QR code containing team_number and branch_id
  /// QR Format: {"team_number": "1", "branch_id": 1}
  Future<bool> loginWithQR(String qrData) async {
    try {
      // Parse QR JSON
      final qrJson = json.decode(qrData);
      final teamNumber = qrJson['team_number']?.toString();
      final branchId = qrJson['branch_id'] as int?;
      
      if (teamNumber == null || branchId == null) {
        print('QR login error: Missing team_number or branch_id');
        return false;
      }
      
      return loginWithTeamNumber(teamNumber, branchId);
    } catch (e) {
      print('QR login error: $e');
      // Fallback: treat as team_number only (legacy)
      return loginWithTeamNumber(qrData, 1); // Default branch 1
    }
  }
  
  Future<void> logout() async {
    _teamId = null;
    _teamNumber = null;
    _teamName = null;
    _branchId = null;
    _token = null;
    _isLoggedIn = false;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('team_id');
    await prefs.remove('team_number');
    await prefs.remove('team_name');
    await prefs.remove('branch_id');
    await prefs.remove('auth_token');
    
    print('Logged out');
    notifyListeners();
  }
}
