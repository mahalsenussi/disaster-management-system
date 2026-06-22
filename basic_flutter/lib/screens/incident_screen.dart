import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/location_service.dart';

class IncidentScreen extends StatefulWidget {
  const IncidentScreen({super.key});

  @override
  State<IncidentScreen> createState() => _IncidentScreenState();
}

class _IncidentScreenState extends State<IncidentScreen> {
  List<dynamic> _myAssignments = [];
  bool _isLoading = true;
  Map<String, dynamic>? _selectedRoute;

  @override
  void initState() {
    super.initState();
    _loadMyAssignments();
  }

  Future<void> _loadMyAssignments() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final apiService = Provider.of<ApiService>(context, listen: false);
      final authService = Provider.of<AuthService>(context, listen: false);

      final result = await apiService.getTeamAssignments(
        authService.teamId!,
        token: authService.token,
      );

      if (result['success'] == true) {
        setState(() {
          _myAssignments = result['assignments'] ?? [];
        });
      }
    } catch (e) {
      print('Error loading assignments: $e');
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _getRouteToIncident(int incidentId, String incidentLocation) async {
    setState(() {
      _isLoading = true;
    });

    try {
      final apiService = Provider.of<ApiService>(context, listen: false);
      final authService = Provider.of<AuthService>(context, listen: false);
      final locationService = Provider.of<LocationService>(context, listen: false);

      final currentPos = locationService.currentPosition;
      if (currentPos == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('الرجاء انتظار تحديد الموقع'),
            backgroundColor: Colors.orange,
          ),
        );
        return;
      }

      final result = await apiService.post('/api/libya-route', {
        'start': '${currentPos.latitude},${currentPos.longitude}',
        'end': incidentLocation,
        'route_type': 'emergency',
      }, token: authService.token);

      if (result['success'] == true) {
        setState(() {
          _selectedRoute = result['route'];
        });

        // Show route details
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('تفاصيل المسار'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('المسافة: ${result['route']['statistics']['total_distance']?.toStringAsFixed(1) ?? '0'} كم'),
                Text('المدة: ${result['route']['statistics']['total_time']?.toStringAsFixed(0) ?? '0'} دقيقة'),
                Text('نقاط الطريق: ${result['route']['statistics']['waypoints'] ?? '0'}'),
                const SizedBox(height: 16),
                const Text('هل تريد بدء التنقل؟'),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('إلغاء'),
              ),
              ElevatedButton(
                onPressed: () {
                  Navigator.pop(context);
                  // Navigate to map with route
                  Navigator.pushNamed(context, '/map');
                },
                child: const Text('بدء التنقل'),
              ),
            ],
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('فشل حساب المسار: ${result['error']}'),
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
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('مهام الفريق'),
        backgroundColor: Colors.blue.shade800,
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _myAssignments.isEmpty
              ? _buildEmptyState()
              : _buildAssignmentsList(),
      floatingActionButton: FloatingActionButton(
        onPressed: _loadMyAssignments,
        backgroundColor: Colors.blue.shade800,
        child: const Icon(Icons.refresh),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.assignment_late, size: 80, color: Colors.grey.shade400),
          const SizedBox(height: 16),
          const Text(
            'لا توجد مهام حالية',
            style: TextStyle(fontSize: 18, color: Colors.grey),
          ),
          const SizedBox(height: 8),
          const Text(
            'سيتم إشعارك عند وجود مهمة جديدة',
            style: TextStyle(color: Colors.grey),
          ),
        ],
      ),
    );
  }

  Widget _buildAssignmentsList() {
    return ListView.builder(
      padding: const EdgeInsets.all(16.0),
      itemCount: _myAssignments.length,
      itemBuilder: (context, index) {
        final assignment = _myAssignments[index];
        return Card(
          margin: const EdgeInsets.only(bottom: 12.0),
          elevation: 4,
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    CircleAvatar(
                      backgroundColor: _getStatusColor(assignment['status']),
                      child: Icon(
                        _getStatusIcon(assignment['status']),
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            assignment['incident_type'] ?? 'حادث',
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            _getStatusText(assignment['status']),
                            style: TextStyle(
                              color: _getStatusColor(assignment['status']),
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  assignment['description'] ?? 'لا يوجد وصف',
                  style: TextStyle(color: Colors.grey.shade700),
                ),
                const SizedBox(height: 8),
                if (assignment['location'] != null)
                  Row(
                    children: [
                      Icon(Icons.location_on, size: 16, color: Colors.grey.shade600),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          assignment['location'],
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      ),
                    ],
                  ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    if (assignment['status'] == 'assigned')
                      ElevatedButton.icon(
                        onPressed: () => _getRouteToIncident(
                          assignment['incident_id'],
                          assignment['location'] ?? '',
                        ),
                        icon: const Icon(Icons.navigation),
                        label: const Text('الحصول على المسار'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue.shade800,
                          foregroundColor: Colors.white,
                        ),
                      ),
                    const SizedBox(width: 8),
                    if (assignment['status'] == 'in_progress')
                      ElevatedButton.icon(
                        onPressed: () {
                          // Update status to completed
                        },
                        icon: const Icon(Icons.check),
                        label: const Text('إنهاء المهمة'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green,
                          foregroundColor: Colors.white,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  IconData _getStatusIcon(String? status) {
    switch (status) {
      case 'assigned':
        return Icons.assignment;
      case 'in_progress':
        return Icons.play_arrow;
      case 'completed':
        return Icons.check_circle;
      default:
        return Icons.help;
    }
  }

  Color _getStatusColor(String? status) {
    switch (status) {
      case 'assigned':
        return Colors.orange;
      case 'in_progress':
        return Colors.blue;
      case 'completed':
        return Colors.green;
      default:
        return Colors.grey;
    }
  }

  String _getStatusText(String? status) {
    switch (status) {
      case 'assigned':
        return 'معين';
      case 'in_progress':
        return 'قيد التنفيذ';
      case 'completed':
        return 'مكتمل';
      default:
        return 'غير معروف';
    }
  }
}
