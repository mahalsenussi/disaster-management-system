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
import '../services/poi_service.dart';
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
  Timer? _destinationTimer;
  
  bool _isNavigationMode = false;
  bool _userPanned = false;
  int _nearestRouteIndex = 0;
  String? _lastEventTimestamp;
  
  // Custom destination navigation (management-sent point or POI selected by
  // the team, e.g. a hospital, after reaching the incident).
  List<List<double>>? _customNavPath;
  double _customNavDistance = 0;
  double _customNavDuration = 0;
  String _customNavLabel = '';
  LatLng? _customNavEnd;
  int? _lastDestId;
  bool _isLoadingRoute = false;

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
    _destinationTimer?.cancel();
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
    
    // Poll for management-sent destinations every 10 seconds
    _destinationTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _checkDestination(teamId);
    });
  }

  List<List<double>> _activeNavPath(RouteService routeService) {
    if (_customNavPath != null && _customNavPath!.isNotEmpty) {
      return _customNavPath!;
    }
    final route = routeService.currentRoute;
    if (route != null && route.route.path.isNotEmpty) {
      return route.route.path;
    }
    return const [];
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
      // Clear custom destination when starting drive mode so incident route takes priority
      _customNavPath = null;
      _customNavDistance = 0;
      _customNavDuration = 0;
      _customNavLabel = '';
      _customNavEnd = null;
      _lastDestId = null;
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
    final path = _activeNavPath(routeService);
    if (path.isEmpty) return;
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
          if (!_isNavigationMode) _buildPoiLegend(),
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
                  _buildSelfMarker(currentPosition, authService),
                ],
              ),
            MarkerLayer(
              markers: _buildTeamMarkers(authService, teamService),
            ),
            MarkerLayer(
              markers: _buildIncidentMarkers(incidentService),
            ),
            Consumer<PoiService>(
              builder: (context, poiService, _) {
                return MarkerLayer(
                  markers: _buildPoiMarkers(poiService),
                );
              },
            ),
            Consumer<RouteService>(
              builder: (context, routeService, _) {
                final path = _activeNavPath(routeService);
                if (path.isNotEmpty) {
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
                final path = _activeNavPath(routeService);
                if (path.isEmpty) return const SizedBox.shrink();
                final lastPoint = _customNavEnd != null
                    ? [_customNavEnd!.latitude, _customNavEnd!.longitude]
                    : path.last;
                return MarkerLayer(
                  markers: [
                    Marker(
                      point: LatLng(lastPoint[0], lastPoint[1]),
                      width: 44,
                      height: 44,
                      child: _customNavEnd != null
                          ? const Icon(
                              Icons.flag,
                              color: Color(0xFF8E44AD),
                              size: 44,
                            )
                          : const Icon(
                              Icons.location_on,
                              color: Colors.red,
                              size: 40,
                            ),
                    ),
                  ],
                );
              },
            ),
            if (_customNavEnd != null)
              MarkerLayer(
                markers: [
                  Marker(
                    point: _customNavEnd!,
                    width: 80,
                    height: 40,
                    child: Text(
                      _customNavLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                        backgroundColor: Color(0xE68E44AD),
                      ),
                    ),
                  ),
                ],
              ),
          ],
        );
      },
    );
  }

  Marker _buildSelfMarker(dynamic position, AuthService authService) {
    final teamNumber = authService.teamNumber ?? '';
    final teamName = authService.teamName ?? '';
    return Marker(
      point: LatLng(position.latitude, position.longitude),
      width: 80,
      height: 80,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
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
          Text(
            teamNumber.isNotEmpty ? teamNumber : 'You',
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: Colors.white,
              backgroundColor: Colors.blue,
            ),
          ),
          if (teamName.isNotEmpty)
            Text(
              teamName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 10,
                color: Colors.blue,
                backgroundColor: Colors.white70,
              ),
            ),
        ],
      ),
    );
  }

  List<Marker> _buildTeamMarkers(AuthService authService, TeamService teamService) {
    final selfTeamId = int.tryParse(authService.teamId ?? '0') ?? 0;
    
    return teamService.teams
        .where((t) => t.id != selfTeamId)
        .map((team) {
      final color = _getGpsColor(team.gpsState);
      final label = team.teamNumber?.isNotEmpty == true
          ? team.teamNumber!
          : (team.name.isNotEmpty ? team.name : 'Team ${team.id}');

      return Marker(
        point: LatLng(team.lat, team.lng),
        width: 80,
        height: 60,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
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
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: color == Colors.grey ? Colors.black87 : Colors.white,
                backgroundColor: color == Colors.grey
                    ? Colors.white.withOpacity(0.85)
                    : color.withOpacity(0.9),
              ),
            ),
          ],
        ),
      );
    }).toList();
  }

  List<Marker> _buildPoiMarkers(PoiService poiService) {
    return poiService.visiblePois.map((poi) {
      final color = poiCategoryColor(poi.category);
      final label = poiCategoryLabel(poi.category);
      final name = (poi.name != null && poi.name!.isNotEmpty)
          ? poi.name!
          : label;

      return Marker(
        point: LatLng(poi.lat, poi.lng),
        width: 16,
        height: 16,
        child: GestureDetector(
          onTap: () {
            showDialog<void>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: Text(name),
                content: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: color,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(label, style: const TextStyle(fontSize: 14)),
                      ],
                    ),
                    if (poi.address != null && poi.address!.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        poi.address!,
                        style: const TextStyle(fontSize: 13),
                      ),
                    ],
                  ],
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(ctx).pop(),
                    child: const Text('Close'),
                  ),
                ],
              ),
            );
          },
          child: Container(
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 2),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.3),
                  blurRadius: 3,
                  offset: const Offset(0, 1),
                ),
              ],
            ),
          ),
        ),
      );
    }).toList();
  }

  Widget _buildPoiLegend() {
    return Consumer<PoiService>(
      builder: (context, poiService, _) {
        final chips = <Widget>[
          for (final category in kPoiCategories)
            _PoiLegendChip(
              label: poiCategoryLabel(category),
              color: poiCategoryColor(category),
              visible: poiService.isCategoryVisible(category),
              onTap: () => poiService.toggleCategory(category),
            ),
        ];

        return Positioned(
          left: 8,
          right: 8,
          bottom: 8,
          child: IgnorePointer(
            ignoring: false,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              reverse: true,
              child: Row(
                children: [
                  if (poiService.pois.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(6),
                      child: Text(
                        'No POIs in area',
                        style: TextStyle(fontSize: 11),
                      ),
                    ),
                  ...chips,
                ],
              ),
            ),
          ),
        );
      },
    );
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
                  if (_customNavEnd != null && !_isNavigationMode) ...[
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF8E44AD).withOpacity(0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        '📍 ${_customNavLabel.isEmpty ? "New destination received" : _customNavLabel} — tap Start Drive Mode',
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF8E44AD),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],
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
        if (position == null) return const SizedBox.shrink();
        
        final path = _activeNavPath(routeService);
        if (path.isEmpty) return const SizedBox.shrink();
        
        final speed = position.speed * 3.6; // m/s to km/h
        final totalDistance = _customNavPath != null ? _customNavDistance : (routeService.currentRoute?.route.distance ?? 0);
        final progress = path.isNotEmpty ? _nearestRouteIndex / path.length : 0.0;
        
        final double distanceLeft;
        if (_customNavPath != null && _customNavPath!.isNotEmpty) {
          // Scale remaining distance by position on custom path (linear approximation
          // between accumulated real-world distances and index-based progress)
          distanceLeft = totalDistance * (1 - progress);
        } else {
          distanceLeft = totalDistance * (1 - progress);
        }
        final eta = distanceLeft / (speed < 1.0 ? 1.0 : speed) * 60; // min

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
                if (_customNavEnd != null && _customNavLabel.isNotEmpty) ...[
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8E44AD).withOpacity(0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '📍 ${_customNavLabel}',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF8E44AD),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
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
                    Text('${distanceLeft.toStringAsFixed(1)} km remaining'),
                  ],
                ),
                if (_customNavEnd != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      const Icon(Icons.access_time, size: 18),
                      const SizedBox(width: 8),
                      Text('${eta.toStringAsFixed(1)} min ETA'),
                    ],
                  ),
                ],
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => _toggleNavigationMode(false),
                          icon: const Icon(Icons.close),
                          label: const Text('Close Drive Mode'),
                        ),
                      ),
                      if (_customNavEnd != null) ...[
                        const SizedBox(width: 8),
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _clearCustomNav,
                            icon: const Icon(Icons.clear),
                            label: const Text('Clear Dest'),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (_isNavigationMode && _customNavEnd == null) ...[
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _pickPoiDestination,
                      icon: const Icon(Icons.add_location),
                      label: const Text('Go to POI'),
                    ),
                  ),
                ],
                if (_isNavigationMode && _customNavEnd != null) ...[
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _pickPoiDestination,
                      icon: const Icon(Icons.add_location),
                      label: const Text('Change Destination'),
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
  
  Future<void> _pickPoiDestination() async {
    final poiService = context.read<PoiService>();
    if (poiService.pois.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No POIs available. Add points first on the dashboard.'), duration: Duration(seconds: 3)),
        );
      }
      return;
    }
    
    final selected = await showModalBottomSheet<Poi>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) {
        final sorted = List<Poi>.from(poiService.visiblePois)..sort((a, b) => poiCategoryLabel(a.category).compareTo(poiCategoryLabel(b.category)));
        return DraggableScrollableSheet(
          initialChildSize: 0.65,
          maxChildSize: 0.85,
          minChildSize: 0.3,
          expand: false,
          builder: (_, ctrl) => Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(14),
                child: Text('Go to POI', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
              Expanded(
                child: ListView.builder(
                  controller: ctrl,
                  itemCount: sorted.length,
                  itemBuilder: (_, i) {
                    final poi = sorted[i];
                    final color = poi.category == 'hospital'
                        ? Colors.red
                        : poi.category == 'shelter'
                            ? Colors.blue
                            : poi.category == 'warehouse'
                                ? Colors.orange
                                : poi.category == 'police_station'
                                    ? Colors.indigo
                                    : poi.category == 'fire_station'
                                        ? Colors.deepOrange
                                        : Colors.grey;
                    final catLabel = poi.category.replaceAll('_', ' ');
                    return ListTile(
                      leading: Icon(Icons.circle, color: color, size: 16),
                      title: Text(
                        poi.name != null && poi.name!.isNotEmpty ? poi.name! : poiCategoryLabel(poi.category),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        catLabel,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      onTap: () => Navigator.pop(ctx, poi),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
    
    if (selected == null || !mounted) return;
    
    final label = [
      selected.category.replaceAll('_', ' '),
      if (selected.name != null && selected.name!.isNotEmpty) selected.name,
    ].join(' - ');
    
    await _navigateToCustomPoint(selected.lat, selected.lng, label);
  }
  
  Future<void> _navigateToCustomPoint(double destLat, double destLng, String label, {bool announce = false, int? destId}) async {
    final locationService = context.read<LocationService>();
    final pos = locationService.currentPosition;
    setState(() { _isLoadingRoute = true; });
    
    try {
      final payload = <String, dynamic>{
        'destination': {'lat': destLat, 'lng': destLng},
      };
      if (pos != null) {
        payload['origin'] = {'lat': pos.latitude, 'lng': pos.longitude};
      }
      
      final resp = await ApiService.post('/api/routes/to-point', payload, requireAuth: true);
      final raw = (resp['path'] as List? ?? []);
      final path = raw
          .map((p) => [((p as List)[0]).toDouble(), (p[1]).toDouble()])
          .toList() as List<List<double>>;
      
      if (path.isEmpty) {
        final originLat = pos?.latitude ?? destLat;
        final originLng = pos?.longitude ?? destLng;
        path.addAll([
          [originLat, originLng],
          [destLat, destLng],
        ]);
      }
      
      setState(() {
        _customNavPath = path;
        _customNavDistance = (resp['distance'] ?? 0.0).toDouble();
        _customNavDuration = (resp['duration'] ?? 0.0).toDouble();
        _customNavLabel = label;
        _customNavEnd = LatLng(destLat, destLng);
        if (destId != null) _lastDestId = destId;
        _nearestRouteIndex = 0;
        _userPanned = false;
      });
      
      if (announce && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('📍 Now navigating to: $label'),
            duration: const Duration(seconds: 4),
            backgroundColor: const Color(0xFF8E44AD),
          ),
        );
      }
    } catch (e) {
      // Fallback: straight-line
      final originLat = pos?.latitude ?? destLat;
      final originLng = pos?.longitude ?? destLng;
      setState(() {
        _customNavPath = [
          [originLat, originLng],
          [destLat, destLng],
        ];
        _customNavDistance = Geolocator.distanceBetween(originLat, originLng, destLat, destLng) / 1000;
        _customNavDuration = _customNavDistance / 40.0 * 3600; // ~40 km/h
        _customNavLabel = label;
        _customNavEnd = LatLng(destLat, destLng);
        if (destId != null) _lastDestId = destId;
        _nearestRouteIndex = 0;
        _userPanned = false;
      });
      
      if (announce && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('📍 Navigating to: $label (straight line — routing unavailable)'),
            duration: const Duration(seconds: 4),
            backgroundColor: const Color(0xFF8E44AD),
          ),
        );
      }
    } finally {
      if (mounted) setState(() { _isLoadingRoute = false; });
    }
  }
  
  void _clearCustomNav() {
    setState(() {
      _customNavPath = null;
      _customNavDistance = 0;
      _customNavDuration = 0;
      _customNavLabel = '';
      _customNavEnd = null;
      _lastDestId = null;
      _nearestRouteIndex = 0;
      _userPanned = false;
    });
  }
  
  Future<void> _checkDestination(int teamId) async {
    try {
      final resp = await ApiService.get('/api/teams/$teamId/destination', requireAuth: true);
      if (resp is! Map || resp['active'] != true) return;
      
      final dynamic rawId = resp['id'];
      final int id = rawId is int ? rawId : int.tryParse(rawId?.toString() ?? '') ?? 0;
      if (id == 0) return;
      if (id == _lastDestId) return;
      
      final dynamic rawLat = resp['lat'];
      final dynamic rawLng = resp['lng'];
      if (rawLat == null || rawLng == null) return;
      final double destLat = (rawLat is num) ? rawLat.toDouble() : double.tryParse(rawLat.toString()) ?? 0;
      final double destLng = (rawLng is num) ? rawLng.toDouble() : double.tryParse(rawLng.toString()) ?? 0;
      if (destLat == 0 && destLng == 0) return;
      
      final String label = (resp['label']?.toString() ?? 'Destination').trim();
      await _navigateToCustomPoint(destLat, destLng, label, announce: true, destId: id);
    } catch (e) {
      print('[MapScreen] _checkDestination error: $e');
    }
  }
}

class _PoiLegendChip extends StatelessWidget {
  final String label;
  final Color color;
  final bool visible;
  final VoidCallback onTap;

  const _PoiLegendChip({
    required this.label,
    required this.color,
    required this.visible,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(visible ? 0.92 : 0.4),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: color, width: 1.5),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: color,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 5),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  color: visible ? Colors.black87 : Colors.grey,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
