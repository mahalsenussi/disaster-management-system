import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:geolocator/geolocator.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final TextEditingController _teamNumberController = TextEditingController();
  bool _isLoading = false;
  bool _showScanner = false;
  String? _errorMessage;
  
  List<Map<String, dynamic>> _branches = [];
  int? _selectedBranchId;
  bool _isLoadingBranches = true;
  
  double? _lat;
  double? _lng;
  bool _isDetectingLocation = false;
  String? _detectedBranchName;
  String? _detectionWarning;

  @override
  void initState() {
    super.initState();
    _loadBranches();
    _detectLocation();
  }

  Future<void> _loadBranches() async {
    try {
      final branches = await ApiService.getBranches();
      if (mounted) {
        setState(() {
          _branches = branches;
          _selectedBranchId = branches.isNotEmpty ? branches[0]['id'] as int : null;
          _isLoadingBranches = false;
        });
      }
    } catch (e) {
      print('Error loading branches: $e');
      if (mounted) {
        setState(() {
          _isLoadingBranches = false;
          _errorMessage = 'Failed to load branches';
        });
      }
    }
  }

  /// Detect the team's area from GPS so the branch is assigned automatically
  /// (teams can be shared between areas).
  Future<void> _detectLocation() async {
    if (_isDetectingLocation) return;
    setState(() {
      _isDetectingLocation = true;
      _detectionWarning = null;
    });

    Position? position;
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (!serviceEnabled) {
        _detectionWarning = 'Location service off - select branch manually';
      } else if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        _detectionWarning = 'Location permission denied - select branch manually';
      } else {
        position = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.low,
        ).timeout(const Duration(seconds: 20));
      }
    } catch (e) {
      print('Location detection error: $e');
      _detectionWarning = 'Could not detect location - select branch manually';
    }

    if (!mounted) return;

    if (position != null) {
      _lat = position.latitude;
      _lng = position.longitude;
      final branch = await ApiService.geoLocateBranch(position.latitude, position.longitude);
      if (mounted) {
        if (branch != null) {
          setState(() {
            _detectedBranchName = '${branch['name']}'
                '${branch['match_type'] == 'nearest' ? ' (nearest area)' : ''}';
            _selectedBranchId = branch['id'];
            if (branch['match_type'] == 'nearest') {
              _detectionWarning =
                  'Outside branch radius - using nearest area (${branch['city']})';
            }
          });
        } else {
          setState(() {
            _detectionWarning = 'Location not in any branch area - select manually';
          });
        }
      }
    } else {
      _detectionWarning ??= 'No GPS fix - select branch manually';
    }

    if (mounted) {
      setState(() => _isDetectingLocation = false);
    }
  }

  @override
  void dispose() {
    _teamNumberController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    final teamNumber = _teamNumberController.text.trim();
    final branchId = _selectedBranchId;
    
    if (teamNumber.isEmpty) {
      setState(() => _errorMessage = 'Please enter team number');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final authService = context.read<AuthService>();
    final success = await authService.loginWithTeamNumber(
      teamNumber,
      branchId: branchId,
      lat: _lat,
      lng: _lng,
    );

    setState(() => _isLoading = false);

    if (!success && mounted) {
      setState(() => _errorMessage = 'Team not found for your area');
    }
  }

  void _onQRDetected(String code) {
    setState(() {
      _showScanner = false;
      _teamNumberController.text = code;
    });
    _login();
  }

  @override
  Widget build(BuildContext context) {
    if (_showScanner) {
      return _QRScannerScreen(onDetected: _onQRDetected);
    }

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(
                  Icons.emergency,
                  size: 80,
                  color: Colors.red,
                ),
                const SizedBox(height: 24),
                const Text(
                  'Emergency Field Ops',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 48),
                TextField(
                  controller: _teamNumberController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Team Number',
                    hintText: 'Enter your team number',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.badge),
                  ),
                  onSubmitted: (_) => _login(),
                ),
                const SizedBox(height: 16),
                if (_isDetectingLocation)
                  const Row(
                    children: [
                      SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Detecting your location...',
                          style: TextStyle(fontSize: 13),
                        ),
                      ),
                    ],
                  )
                else if (_detectedBranchName != null) ...[
                  Row(
                    children: [
                      const Icon(Icons.my_location, size: 16, color: Colors.green),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Area auto-detected: $_detectedBranchName',
                          style: const TextStyle(fontSize: 13, color: Colors.green),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
                if (_detectionWarning != null) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      const Icon(Icons.warning_amber, size: 16, color: Colors.orange),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _detectionWarning!,
                          style: const TextStyle(fontSize: 13, color: Colors.orange),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 12),
                if (_isLoadingBranches)
                  const CircularProgressIndicator()
                else if (_branches.isEmpty)
                  const Text(
                    'No branches available',
                    style: TextStyle(color: Colors.orange),
                  )
                else
                  DropdownButtonFormField<int>(
                    value: _selectedBranchId,
                    decoration: const InputDecoration(
                      labelText: 'Branch (auto)',
                      hintText: 'Manually override if needed',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.location_city),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 16),
                    ),
                    isExpanded: true,
                    items: _branches.map((branch) {
                      return DropdownMenuItem<int>(
                        value: branch['id'] as int,
                        child: Text(
                          '${branch['name']} (${branch['city']})',
                          style: const TextStyle(fontSize: 14),
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    }).toList(),
                    onChanged: (value) {
                      setState(() {
                        _selectedBranchId = value;
                      });
                    },
                  ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 16),
                  Text(
                    _errorMessage!,
                    style: const TextStyle(color: Colors.red),
                  ),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _isLoading ? null : _login,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: _isLoading
                        ? const CircularProgressIndicator(color: Colors.white)
                        : const Text('Login', style: TextStyle(fontSize: 16)),
                  ),
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: () => setState(() => _showScanner = true),
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('Scan QR Code'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    minimumSize: const Size(double.infinity, 48),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _QRScannerScreen extends StatefulWidget {
  final Function(String) onDetected;

  const _QRScannerScreen({required this.onDetected});

  @override
  State<_QRScannerScreen> createState() => _QRScannerScreenState();
}

class _QRScannerScreenState extends State<_QRScannerScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan QR Code'),
      ),
      body: MobileScanner(
        onDetect: (capture) {
          final barcode = capture.barcodes.first;
          if (barcode.rawValue != null) {
            widget.onDetected(barcode.rawValue!);
          }
        },
      ),
    );
  }
}
