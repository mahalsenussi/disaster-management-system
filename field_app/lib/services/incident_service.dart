import 'dart:async';
import 'package:flutter/foundation.dart';
import 'api_service.dart';

class Incident {
  final int id;
  final String type;
  final String severity;
  final double lat;
  final double lng;
  final String status;
  final String? description;
  final String createdAt;
  final int? assignedTeamId;
  
  Incident({
    required this.id,
    required this.type,
    required this.severity,
    required this.lat,
    required this.lng,
    required this.status,
    this.description,
    required this.createdAt,
    this.assignedTeamId,
  });
  
  factory Incident.fromJson(Map<String, dynamic> json) {
    return Incident(
      id: json['id'],
      type: json['type'] ?? '',
      severity: json['severity'] ?? 'medium',
      lat: (json['lat'] ?? 0.0).toDouble(),
      lng: (json['lng'] ?? 0.0).toDouble(),
      status: json['status'] ?? 'open',
      description: json['description'],
      createdAt: json['created_at'] ?? '',
      assignedTeamId: json['assigned_team_id'],
    );
  }
}

class IncidentService with ChangeNotifier {
  List<Incident> _incidents = [];
  bool _isLoading = false;
  bool _isOffline = false;
  Timer? _refreshTimer;
  
  List<Incident> get incidents => _incidents;
  bool get isLoading => _isLoading;
  bool get isOffline => _isOffline;
  
  IncidentService() {
    startAutoRefresh();
  }
  
  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }
  
  void startAutoRefresh() {
    fetchIncidents();
    _refreshTimer = Timer.periodic(const Duration(seconds: 8), (_) {
      fetchIncidents();
    });
  }
  
  Future<void> fetchIncidents() async {
    if (_isLoading) return;
    
    _isLoading = true;
    notifyListeners();
    
    try {
      final response = await ApiService.get('/api/incidents', requireAuth: true);
      final incidentsList = response as List;
      
      _incidents = incidentsList.map((i) => Incident.fromJson(i)).toList();
      _isOffline = false;
      print('Incidents fetched: ${_incidents.length}');
    } catch (e) {
      print('Fetch incidents error: $e');
      _isOffline = true;
      // Keep last data on error
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
  
  Incident? getIncidentById(int id) {
    try {
      return _incidents.firstWhere((i) => i.id == id);
    } catch (e) {
      return null;
    }
  }
}
