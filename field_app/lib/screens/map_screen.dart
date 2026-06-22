import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import '../services/auth_service.dart';
import '../services/team_service.dart';
import '../services/incident_service.dart';
import '../services/route_service.dart';
import '../services/location_service.dart';
import '../services/api_service.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _mapController = MapController();
  Timer? _rerouteCheckTimer;
  Timer? _navUpdateTimer;
  Timer? _recenterTimer;
  Timer? _eventsTimer;
  
  bool _isNavigationMode = false;
  bool _userPanned = false;
  int _nearestRouteIndex = 0;
  String? _lastEventTimestamp;

  @override
  void initState() {
    super.initState();
    _initializeServices();
    // Keep screen on for GPS tracking
    WakelockPlus.enable();
  }

  @override
  void dispose() {
    _rerouteCheckTimer?.cancel();
    _navUpdateTimer?.cancel();
    _recenterTimer?.cancel();
    _eventsTimer?.cancel();
    WakelockPlus.disable();
    super.dispose();
  }

  void _initializeServices() {
    final authService = context.read<AuthService>();
    final teamId = int.tryParse(authService.teamId ?? '0') ?? 0;
    
    // Start location tracking
    final locationService = context.read<LocationService>();
    locationService.startTracking();
    
    // Listen to location changes for navigation
    locationService.addListener(_onLocationUpdate);
    
    // Start route refresh
    final routeService = context.read<RouteService>();
    routeService.startAutoRefresh(teamId);
    
    // Check for rerouting every 5 seconds
    _rerouteCheckTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _checkReroute();
    });
    
    // Poll for assignment events every 5 seconds
    _eventsTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _checkEvents(teamId);
    });
  }
  
  void _onLocationUpdate() {
    if (!_isNavigationMode) return;
    
    final locationService = context.read<LocationService>();
    final position = locationService.currentPosition;
    
    if (position == null) {
      // GPS lost - stop navigation
      _toggleNavigationMode(false);
      return;
    }
    
    if (!_userPanned) {
      // Auto-center on user
      _mapController.move(
        LatLng(position.latitude, position.longitude),
        17.0,
      );
    }
    
    // Update route progress
    _updateRouteProgress(LatLng(position.latitude, position.longitude));
  }
  
  void _centerOnLocation() {
    final locationService = context.read<LocationService>();
    final position = locationService.currentPosition;
    if (position != null) {
      _mapController.move(LatLng(position.latitude, position.longitude), 15.0);
      _userPanned = false;
    }
  }
  
  void _toggleNavigationMode(bool? value) {
    setState(() {
      _isNavigationMode = value ?? !_isNavigationMode;
      _userPanned = false;
      _nearestRouteIndex = 0;
    });
    
    if (_isNavigationMode) {
      // Start navigation
      final locationService = context.read<LocationService>();
      final position = locationService.currentPosition;
      if (position != null) {
        _mapController.move(
          LatLng(position.latitude, position.longitude),
          17.0,
        );
      }
    }
  }
  
  void _onMapMove() {
    if (_isNavigationMode) {
      _userPanned = true;
      _recenterTimer?.cancel();
      _recenterTimer = Timer(const Duration(seconds: 5), () {
        _userPanned = false;
      });
    }
  }
  
  void _updateRouteProgress(LatLng currentPos) {
    final routeService = context.read<RouteService>();
    final route = routeService.currentRoute;
    if (route == null || route.route.path.isEmpty) return;
    
    final path = route.route.path;
    double minDistance = double.infinity;
    int nearestIndex = 0;
    
    for (int i = 0; i < path.length; i++) {
      final point = LatLng(path[i][0], path[i][1]);
      final distance = Geolocator.distanceBetween(
        currentPos.latitude,
        currentPos.longitude,
        point.latitude,
        point.longitude,
      );
      if (distance < minDistance) {
        minDistance = distance;
        nearestIndex = i;
      }
    }
    
    if (nearestIndex != _nearestRouteIndex) {
      setState(() {
        _nearestRouteIndex = nearestIndex;
      });
    }
  }

  void _checkReroute() async {
    // Reroute not available on server
    return;
  }

  void _checkEvents(int teamId) async {
    try {
      final events = await ApiService.get('/api/events', requireAuth: true);
      if (events == null || events is! List) return;
      
      final newEvents = _lastEventTimestamp != null
          ? events.where((e) => e is Map && (e['timestamp']?.toString().compareTo(_lastEventTimestamp!) ?? 0) > 0).toList()
          : events;
      
      for (final event in newEvents) {
        if (event is! Map) continue;
        final eventType = event['type']?.toString();
        final eventTeamId = event['team_id'];
        
        if (eventType == 'incident_assigned' && eventTeamId == teamId) {
          final incidentId = event['incident_id'];
          if (mounted && context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('You have been assigned to incident #$incidentId'),
                backgroundColor: Colors.orange,
                duration: const Duration(seconds: 5),
              ),
            );
            // Refresh route and incidents for the team
            context.read<RouteService>().fetchRoute(teamId);
            context.read<IncidentService>().fetchIncidents();
          }
        } else if (eventType == 'incident_new' && mounted && context.mounted) {
          // Optional: notify team of new incidents in area
          context.read<IncidentService>().fetchIncidents();
        }
      }
      
      if (events.isNotEmpty) {
        _lastEventTimestamp = events.last['timestamp']?.toString();
      }
    } catch (e) {
      // Silently ignore event polling errors
      print('Event polling error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Field Operations'),
        actions: [
          Consumer3<TeamService, IncidentService, RouteService>(
            builder: (context, teamService, incidentService, routeService, _) {
              if (teamService.isOffline || incidentService.isOffline) {
                return const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16.0),
                  child: Center(
                    child: Row(
                      children: [
                        Icon(Icons.cloud_off, color: Colors.orange, size: 20),
                        SizedBox(width: 4),
                        Text('Offline', style: TextStyle(color: Colors.orange)),
                      ],
                    ),
                  ),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () {
              context.read<LocationService>().stopTracking();
              context.read<RouteService>().stopAutoRefresh();
              context.read<AuthService>().logout();
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          _buildMap(),
          _buildReroutingIndicator(),
          _buildIncidentBadge(),
          _buildInfoPanel(),
          Positioned(
            right: 16,
            bottom: 80,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                FloatingActionButton(
                  mini: true,
                  heroTag: 'nav',
                  onPressed: () => _toggleNavigationMode(null),
                  backgroundColor: _isNavigationMode ? Colors.blue : Colors.white,
                  foregroundColor: _isNavigationMode ? Colors.white : Colors.blue,
                  child: Icon(
                    _isNavigationMode ? Icons.navigation : Icons.navigation_outlined,
                  ),
                ),
                const SizedBox(height: 8),
                FloatingActionButton(
                  mini: true,
                  heroTag: 'center',
                  onPressed: _centerOnLocation,
                  child: const Icon(Icons.my_location),
                ),
              ],
            ),
          ),
          if (_isNavigationMode) _buildNavigationPanel(),
        ],
      ),
    );
  }

  Widget _buildMap() {
    return Consumer4<AuthService, LocationService, TeamService, IncidentService>(
      builder: (context, authService, locationService, teamService, incidentService, _) {
        final currentPosition = locationService.currentPosition;
        
        return FlutterMap(
          mapController: _mapController,
          options: MapOptions(
            initialCenter: currentPosition != null
                ? LatLng(currentPosition.latitude, currentPosition.longitude)
                : const LatLng(32.8872, 13.1913),
            initialZoom: 13.0,
            minZoom: 10.0,
            maxZoom: 18.0,
            onMapEvent: (event) {
              if (event is MapEventMoveEnd) {
                _onMapMove();
              }
            },
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.libya.field_app',
            ),
            if (currentPosition != null)
              MarkerLayer(
                markers: [
                  _buildSelfMarker(currentPosition),
                ],
              ),
            MarkerLayer(
              markers: _buildTeamMarkers(authService, teamService),
            ),
            MarkerLayer(
              markers: _buildIncidentMarkers(incidentService),
            ),
            Consumer<RouteService>(
              builder: (context, routeService, _) {
                final route = routeService.currentRoute;
                if (route != null && route.route.path.isNotEmpty) {
                  final path = route.route.path;
                  final completedPath = path.sublist(0, _nearestRouteIndex + 1);
                  final remainingPath = path.sublist(_nearestRouteIndex);
                  
                  return PolylineLayer(
                    polylines: [
                      if (completedPath.length > 1)
                        Polyline(
                          points: completedPath
                              .map((p) => LatLng(p[0], p[1]))
                              .toList(),
                          strokeWidth: 4.0,
                          color: Colors.grey,
                        ),
                      if (remainingPath.length > 1)
                        Polyline(
                          points: remainingPath
                              .map((p) => LatLng(p[0], p[1]))
                              .toList(),
                          strokeWidth: 4.0,
                          color: Colors.blue,
                        ),
                    ],
                  );
                }
                return const SizedBox.shrink();
              },
            ),
            Consumer<RouteService>(
              builder: (context, routeService, _) {
                final route = routeService.currentRoute;
                if (route != null && route.route.path.isNotEmpty) {
                  final lastPoint = route.route.path.last;
                  return MarkerLayer(
                    markers: [
                      Marker(
                        point: LatLng(lastPoint[0], lastPoint[1]),
                        width: 40,
                        height: 40,
                        child: const Icon(
                          Icons.location_on,
                          color: Colors.red,
                          size: 40,
                        ),
                      ),
                    ],
                  );
                }
                return const SizedBox.shrink();
              },
            ),
          ],
        );
      },
    );
  }

  Marker _buildSelfMarker(dynamic position) {
    return Marker(
      point: LatLng(position.latitude, position.longitude),
      width: 50,
      height: 50,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.blue.withOpacity(0.3),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.blue, width: 3),
        ),
        child: const Icon(
          Icons.my_location,
          color: Colors.blue,
          size: 30,
        ),
      ),
    );
  }

  List<Marker> _buildTeamMarkers(AuthService authService, TeamService teamService) {
    final selfTeamId = int.tryParse(authService.teamId ?? '0') ?? 0;
    
    return teamService.teams
        .where((t) => t.id != selfTeamId)
        .map((team) {
      final color = _getGpsColor(team.gpsState);
      
      return Marker(
        point: LatLng(team.lat, team.lng),
        width: 40,
        height: 40,
        child: Container(
          decoration: BoxDecoration(
            color: color.withOpacity(0.5),
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 2),
          ),
          child: Center(
            child: Text(
              team.icon,
              style: const TextStyle(fontSize: 20),
            ),
          ),
        ),
      );
    }).toList();
  }

  List<Marker> _buildIncidentMarkers(IncidentService incidentService) {
    return incidentService.incidents.map((incident) {
      final color = _getSeverityColor(incident.severity);
      
      return Marker(
        point: LatLng(incident.lat, incident.lng),
        width: 40,
        height: 40,
        child: Container(
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 2),
          ),
          child: const Icon(
            Icons.warning,
            color: Colors.white,
            size: 24,
          ),
        ),
      );
    }).toList();
  }

  Color _getGpsColor(String state) {
    switch (state) {
      case 'gps_active':
        return Colors.green;
      case 'gps_lost':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  Color _getSeverityColor(String severity) {
    switch (severity) {
      case 'high':
        return Colors.red;
      case 'medium':
        return Colors.orange;
      case 'low':
        return Colors.yellow;
      default:
        return Colors.grey;
    }
  }

  Widget _buildReroutingIndicator() {
    return Consumer<RouteService>(
      builder: (context, routeService, _) {
        if (!routeService.isRerouting) {
          return const SizedBox.shrink();
        }
        
        return Positioned(
          top: 16,
          left: 16,
          right: 16,
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.blue.withOpacity(0.9),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Row(
              children: [
                SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                ),
                SizedBox(width: 12),
                Text(
                  'Re-routing...',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildIncidentBadge() {
    return Consumer2<RouteService, IncidentService>(
      builder: (context, routeService, incidentService, _) {
        // Hide badge while in navigation/drive mode
        if (_isNavigationMode) {
          return const SizedBox.shrink();
        }
        
        final route = routeService.currentRoute;
        final incident = route != null ? incidentService.getIncidentById(route.incident.id) : null;
        
        if (incident == null) {
          return const SizedBox.shrink();
        }
        
        // Severity color
        Color severityColor = Colors.orange;
        if (incident.severity == '1' || incident.severity == '2') {
          severityColor = Colors.green;
        } else if (incident.severity == '5') {
          severityColor = Colors.red;
        } else if (incident.severity == '4') {
          severityColor = Colors.deepOrange;
        }
        
        return Positioned(
          top: 16,
          left: 16,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.95),
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.warning, color: severityColor, size: 18),
                const SizedBox(width: 6),
                Text(
                  '#${incident.id} ${incident.type}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildInfoPanel() {
    return Consumer2<RouteService, IncidentService>(
      builder: (context, routeService, incidentService, _) {
        // Hide info panel while in navigation/drive mode
        if (_isNavigationMode) {
          return const SizedBox.shrink();
        }
        
        final route = routeService.currentRoute;
        final incident = route != null ? incidentService.getIncidentById(route.incident.id) : null;
        
        // If no active assignment, don't show panel
        if (incident == null) {
          return const SizedBox.shrink();
        }
        
        final distance = route?.route.distance ?? 0.0;
        final duration = route?.route.duration ?? 0.0;
        final eta = duration / 60; // minutes
        
        // Severity color
        Color severityColor = Colors.orange;
        if (incident.severity == '1' || incident.severity == '2') {
          severityColor = Colors.green;
        } else if (incident.severity == '5') {
          severityColor = Colors.red;
        } else if (incident.severity == '4') {
          severityColor = Colors.deepOrange;
        }
        
        return Positioned(
          bottom: 80,
          left: 16,
          right: 16,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.45,
            ),
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.95),
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.2),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Icon(Icons.warning, color: severityColor),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Incident #${incident.id}: ${incident.type}',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Expanded(
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Wrap(
                            spacing: 8,
                            children: [
                              Chip(
                                label: Text('Severity: ${incident.severity}'),
                                backgroundColor: severityColor.withOpacity(0.2),
                                side: BorderSide(color: severityColor),
                                padding: EdgeInsets.zero,
                                labelStyle: TextStyle(color: severityColor, fontSize: 12),
                                visualDensity: VisualDensity.compact,
                              ),
                              Chip(
                                label: Text('Status: ${incident.status}'),
                                padding: EdgeInsets.zero,
                                labelStyle: const TextStyle(fontSize: 12),
                                visualDensity: VisualDensity.compact,
                              ),
                            ],
                          ),
                          if (incident.description != null && incident.description!.isNotEmpty) ...[
                            const SizedBox(height: 8),
                            Text(
                              incident.description!,
                              style: const TextStyle(fontSize: 14),
                            ),
                          ],
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              const Icon(Icons.straighten, size: 18),
                              const SizedBox(width: 6),
                              Text('${distance.toStringAsFixed(1)} km', style: const TextStyle(fontSize: 14)),
                              const SizedBox(width: 16),
                              const Icon(Icons.access_time, size: 18),
                              const SizedBox(width: 6),
                              Text('${eta.toStringAsFixed(1)} min', style: const TextStyle(fontSize: 14)),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () => _toggleNavigationMode(true),
                      icon: const Icon(Icons.navigation),
                      label: const Text('Start Drive Mode'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.blue,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 10),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
  
  Widget _buildNavigationPanel() {
    return Consumer2<LocationService, RouteService>(
      builder: (context, locationService, routeService, _) {
        final position = locationService.currentPosition;
        final route = routeService.currentRoute;
        
        if (position == null || route == null) {
          return const SizedBox.shrink();
        }
        
        final speed = position.speed * 3.6; // m/s to km/h
        final totalDistance = route.route.distance;
        final remainingPoints = route.route.path.length - _nearestRouteIndex;
        final progress = _nearestRouteIndex / route.route.path.length;
        
        return Positioned(
          top: 16,
          left: 16,
          right: 16,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.95),
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 10,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    const Icon(Icons.navigation, color: Colors.blue),
                    const SizedBox(width: 8),
                    const Text(
                      'Navigation',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${speed.toStringAsFixed(0)} km/h',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                LinearProgressIndicator(
                  value: progress,
                  backgroundColor: Colors.grey[300],
                  valueColor: const AlwaysStoppedAnimation<Color>(Colors.blue),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Icon(Icons.straighten, size: 20),
                    const SizedBox(width: 8),
                    Text('${(totalDistance * (1 - progress)).toStringAsFixed(1)} km remaining'),
                  ],
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () => _toggleNavigationMode(false),
                    icon: const Icon(Icons.close),
                    label: const Text('Close Drive Mode'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
