import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/location_service.dart';
import '../services/api_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  List<dynamic> _activeIncidents = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _initializeLocationTracking();
    _loadActiveIncidents();
  }

  Future<void> _initializeLocationTracking() async {
    final authService = Provider.of<AuthService>(context, listen: false);
    final locationService = Provider.of<LocationService>(context, listen: false);
    
    await locationService.startLocationTracking(authService);
    // Start heartbeat for continuous car dashboard operation
    locationService.startHeartbeat(authService);
  }

  Future<void> _loadActiveIncidents() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final apiService = Provider.of<ApiService>(context, listen: false);
      final authService = Provider.of<AuthService>(context, listen: false);
      
      final incidents = await apiService.getActiveIncidents(token: authService.token);
      
      setState(() {
        _activeIncidents = incidents;
        _isLoading = false;
      });
    } catch (e) {
      print('Error loading incidents: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _acceptIncident(int incidentId) async {
    try {
      final apiService = Provider.of<ApiService>(context, listen: false);
      final authService = Provider.of<AuthService>(context, listen: false);
      
      final result = await apiService.acceptIncident(
        authService.teamId!,
        incidentId,
        token: authService.token,
      );

      if (result['success'] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('تم قبول الحادث بنجاح'),
            backgroundColor: Colors.green,
          ),
        );
        _loadActiveIncidents();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('فشل قبول الحادث: ${result['error']}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('خطأ: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final authService = Provider.of<AuthService>(context);
    final locationService = Provider.of<LocationService>(context);

    return Scaffold(
      appBar: AppBar(
        title: Text('فريق: ${authService.teamName ?? authService.teamId}'),
        backgroundColor: Colors.blue.shade800,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              final locationService = Provider.of<LocationService>(context, listen: false);
              await locationService.stopLocationTracking();
              await authService.logout();
            },
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _buildBody(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'الرئيسية',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.map),
            label: 'الخريطة',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.location_on),
            label: 'الموقع',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.warning),
            label: 'الحوادث',
          ),
        ],
        selectedItemColor: Colors.blue.shade800,
        unselectedItemColor: Colors.grey,
        type: BottomNavigationBarType.fixed,
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _loadActiveIncidents,
        backgroundColor: Colors.blue.shade800,
        child: const Icon(Icons.refresh),
      ),
    );
  }

  Widget _buildBody() {
    switch (_currentIndex) {
      case 0:
        return _buildDashboard();
      case 1:
        return _buildMapView();
      case 2:
        return _buildLocationView();
      case 3:
        return _buildIncidentsView();
      default:
        return _buildDashboard();
    }
  }

  Widget _buildDashboard() {
    final authService = Provider.of<AuthService>(context);
    final locationService = Provider.of<LocationService>(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Welcome Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      CircleAvatar(
                        backgroundColor: Colors.blue.shade800,
                        child: const Icon(Icons.group, color: Colors.white),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'مرحباً ${authService.teamName ?? authService.teamId}',
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Text(
                              'الحالة: نشط',
                              style: TextStyle(
                                color: Colors.green.shade600,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Location Status Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'حالة الموقع',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Icon(
                        locationService.isTracking ? Icons.gps_fixed : Icons.gps_off,
                        color: locationService.isTracking ? Colors.green : Colors.red,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        locationService.isTracking ? 'تتبع نشط' : 'التتبع متوقف',
                        style: TextStyle(
                          color: locationService.isTracking ? Colors.green : Colors.red,
                        ),
                      ),
                    ],
                  ),
                  if (locationService.hasLocation) ...[
                    const SizedBox(height: 8),
                    Text('خط العرض: ${locationService.latitude?.toStringAsFixed(6)}'),
                    Text('خط الطول: ${locationService.longitude?.toStringAsFixed(6)}'),
                    if (locationService.accuracy != null)
                      Text('الدقة: ${locationService.accuracy?.toStringAsFixed(1)} متر'),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Active Incidents Summary
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'الحوادث النشطة',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.red.shade100,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          '${_activeIncidents.length}',
                          style: TextStyle(
                            color: Colors.red.shade800,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_activeIncidents.isEmpty)
                    const Text('لا توجد حوادث نشطة حالياً')
                  else
                    ..._activeIncidents.take(3).map((incident) => ListTile(
                      leading: Icon(
                        _getIncidentIcon(incident['type']),
                        color: _getIncidentColor(incident['severity']),
                      ),
                      title: Text(incident['type'] ?? 'حادث'),
                      subtitle: Text(incident['description'] ?? 'لا يوجد وصف'),
                      trailing: ElevatedButton(
                        onPressed: () => _acceptIncident(incident['id']),
                        child: const Text('قبول'),
                      ),
                    )),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMapView() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.map, size: 80, color: Colors.grey.shade400),
          const SizedBox(height: 16),
          const Text('خريطة الفريق'),
          const SizedBox(height: 8),
          ElevatedButton(
            onPressed: () {
              Navigator.pushNamed(context, '/map');
            },
            child: const Text('فتح الخريطة الكاملة'),
          ),
        ],
      ),
    );
  }

  Widget _buildLocationView() {
    final locationService = Provider.of<LocationService>(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  const Icon(Icons.location_on, size: 64, color: Colors.blue),
                  const SizedBox(height: 16),
                  if (locationService.hasLocation) ...[
                    Text(
                      '${locationService.latitude?.toStringAsFixed(6)}',
                      style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                    ),
                    Text(
                      '${locationService.longitude?.toStringAsFixed(6)}',
                      style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 16),
                    if (locationService.accuracy != null)
                      Text('الدقة: ±${locationService.accuracy?.toStringAsFixed(1)} متر'),
                    if (locationService.speed != null && locationService.speed! > 0)
                      Text('السرعة: ${locationService.speed?.toStringAsFixed(1)} م/ث'),
                    if (locationService.heading != null)
                      Text('الاتجاه: ${locationService.heading?.toStringAsFixed(1)}°'),
                  ] else
                    const Text('جاري تحديد الموقع...'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () {
              final locationService = Provider.of<LocationService>(context, listen: false);
              locationService.getCurrentLocation();
            },
            icon: const Icon(Icons.my_location),
            label: const Text('تحديث الموقع'),
          ),
        ],
      ),
    );
  }

  Widget _buildIncidentsView() {
    if (_activeIncidents.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle, size: 80, color: Colors.green.shade300),
            const SizedBox(height: 16),
            const Text(
              'لا توجد حوادث نشطة',
              style: TextStyle(fontSize: 18),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      itemCount: _activeIncidents.length,
      itemBuilder: (context, index) {
        final incident = _activeIncidents[index];
        return Card(
          margin: const EdgeInsets.all(8.0),
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: _getIncidentColor(incident['severity']),
              child: Icon(
                _getIncidentIcon(incident['type']),
                color: Colors.white,
              ),
            ),
            title: Text(incident['type'] ?? 'حادث'),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(incident['description'] ?? 'لا يوجد وصف'),
                if (incident['location'] != null)
                  Text('الموقع: ${incident['location']}'),
              ],
            ),
            isThreeLine: true,
            trailing: ElevatedButton(
              onPressed: () => _acceptIncident(incident['id']),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blue.shade800,
                foregroundColor: Colors.white,
              ),
              child: const Text('قبول'),
            ),
          ),
        );
      },
    );
  }

  IconData _getIncidentIcon(String? type) {
    switch (type?.toLowerCase()) {
      case 'fire':
        return Icons.local_fire_department;
      case 'flood':
        return Icons.water;
      case 'earthquake':
        return Icons.vibration;
      case 'accident':
        return Icons.car_crash;
      default:
        return Icons.warning;
    }
  }

  Color _getIncidentColor(String? severity) {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return Colors.red.shade800;
      case 'high':
        return Colors.red;
      case 'medium':
        return Colors.orange;
      case 'low':
        return Colors.yellow.shade700;
      default:
        return Colors.blue;
    }
  }
}
