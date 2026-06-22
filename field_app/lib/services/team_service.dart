import 'dart:async';
import 'package:flutter/foundation.dart';
import 'api_service.dart';

class Team {
  final int id;
  final String? teamNumber;
  final String name;
  final double lat;
  final double lng;
  final String status;
  final String color;
  final String icon;
  final int batteryLevel;
  final double speed;
  final double heading;
  final bool gpsEnabled;
  final String? lastUpdated;
  final String gpsState;
  
  Team({
    required this.id,
    this.teamNumber,
    required this.name,
    required this.lat,
    required this.lng,
    required this.status,
    required this.color,
    required this.icon,
    required this.batteryLevel,
    required this.speed,
    required this.heading,
    required this.gpsEnabled,
    this.lastUpdated,
    required this.gpsState,
  });
  
  factory Team.fromJson(Map<String, dynamic> json) {
    return Team(
      id: json['id'],
      teamNumber: json['team_number']?.toString(),
      name: json['name'] ?? '',
      lat: (json['lat'] ?? 0.0).toDouble(),
      lng: (json['lng'] ?? 0.0).toDouble(),
      status: json['status'] ?? 'available',
      color: json['color'] ?? '#3498db',
      icon: json['icon'] ?? '🚑',
      batteryLevel: json['battery_level'] ?? 100,
      speed: (json['speed'] ?? 0.0).toDouble(),
      heading: (json['heading'] ?? 0.0).toDouble(),
      gpsEnabled: json['gps_enabled'] == 1,
      lastUpdated: json['last_updated'],
      gpsState: json['gps_state'] ?? 'manual',
    );
  }
}

class TeamService with ChangeNotifier {
  List<Team> _teams = [];
  bool _isLoading = false;
  bool _isOffline = false;
  Timer? _refreshTimer;
  
  List<Team> get teams => _teams;
  bool get isLoading => _isLoading;
  bool get isOffline => _isOffline;
  
  TeamService() {
    startAutoRefresh();
  }
  
  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }
  
  void startAutoRefresh() {
    fetchTeams();
    _refreshTimer = Timer.periodic(const Duration(seconds: 8), (_) {
      fetchTeams();
    });
  }
  
  Future<void> fetchTeams() async {
    if (_isLoading) return;
    
    _isLoading = true;
    notifyListeners();
    
    try {
      final response = await ApiService.get('/api/teams', requireAuth: true);
      final teamsList = response as List;
      
      _teams = teamsList.map((t) => Team.fromJson(t)).toList();
      _isOffline = false;
      print('Teams fetched: ${_teams.length}');
    } catch (e) {
      print('Fetch teams error: $e');
      _isOffline = true;
      // Keep last data on error
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
  
  Team? getTeamById(int id) {
    try {
      return _teams.firstWhere((t) => t.id == id);
    } catch (e) {
      return null;
    }
  }
}
