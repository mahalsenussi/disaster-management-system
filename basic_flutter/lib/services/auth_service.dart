import 'package:flutter/material.dart';
import 'dart:async';
import 'package:shared_preferences/shared_preferences.dart';
import 'location_service.dart';
import 'api_service.dart';

class AuthService extends ChangeNotifier {
  bool _isAuthenticated = false;
  String? _teamId;
  String? _teamName;
  String? _token;
  Map<String, dynamic>? _teamData;

  bool get isAuthenticated => _isAuthenticated;
  String? get teamId => _teamId;
  String? get teamName => _teamName;
  String? get token => _token;
  Map<String, dynamic>? get teamData => _teamData;

  AuthService() {
    _loadStoredAuth();
  }

  Future<void> _loadStoredAuth() async {
    final prefs = await SharedPreferences.getInstance();
    _teamId = prefs.getString('team_id');
    _teamName = prefs.getString('team_name');
    _token = prefs.getString('token');
    _isAuthenticated = _teamId != null; // Only need team_id for v2
    notifyListeners();
  }

  Future<bool> loginWithTeamNumber(String teamNumber) async {
    try {
      // Simple login: just store team_id, no backend validation required
      _teamId = teamNumber;
      _teamName = 'Team $teamNumber';
      _token = null; // No token needed for v2
      _teamData = {'id': teamNumber};
      _isAuthenticated = true;

      // Save to local storage
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('team_id', _teamId!);
      await prefs.setString('team_name', _teamName ?? '');
      await prefs.remove('token'); // Remove old token if exists

      notifyListeners();
      return true;
    } catch (e) {
      print('Login error: $e');
      return false;
    }
  }

  Future<bool> loginWithQRCode(String qrData) async {
    try {
      // QR code contains team ID
      final teamId = qrData; // Simplified: QR data is just team_id
      
      _teamId = teamId;
      _teamName = 'Team $teamId';
      _token = null; // No token needed for v2
      _teamData = {'id': teamId};
      _isAuthenticated = true;

      // Save to local storage
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('team_id', _teamId!);
      await prefs.setString('team_name', _teamName ?? '');
      await prefs.remove('token'); // Remove old token if exists

      notifyListeners();
      return true;
    } catch (e) {
      print('QR login error: $e');
      return false;
    }
  }

  Future<void> logout() async {
    _isAuthenticated = false;
    _teamId = null;
    _teamName = null;
    _token = null;
    _teamData = null;

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('team_id');
    await prefs.remove('team_name');
    await prefs.remove('token');

    notifyListeners();
  }

  Future<void> updateTeamLocation(double lat, double lng) async {
    if (_teamId == null) {
      print('Cannot update location: teamId=$_teamId');
      return;
    }

    try {
      final apiService = ApiService();
      await apiService.updateTeamLocationV2(
        teamId: _teamId!,
        lat: lat,
        lng: lng,
        token: null, // No token needed for v2
      );
    } catch (e) {
      print('Location update error: $e');
      // Keep trying - do not stop tracking
    }
  }

  Future<void> syncLocationToBackend(double lat, double lng, {double? accuracy, double? speed, double? heading}) async {
    if (_teamId == null) return;

    try {
      final apiService = ApiService();
      await apiService.updateTeamLocationV2(
        teamId: _teamId!,
        lat: lat,
        lng: lng,
        token: null, // No token needed for v2
      );
    } catch (e) {
      print('Location sync error: $e');
      // Keep trying - do not stop tracking
    }
  }
}
