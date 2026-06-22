import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'api_service.dart';
import 'auth_service.dart';

class LocationService with ChangeNotifier {
  final AuthService _authService;
  
  Position? _currentPosition;
  bool _isTracking = false;
  bool _hasPermission = false;
  bool _isDisposed = false;
  Timer? _locationTimer;
  Timer? _retryTimer;
  
  // Queue for failed location updates
  final List<Map<String, dynamic>> _locationQueue = [];
  
  Position? get currentPosition => _currentPosition;
  bool get isTracking => _isTracking;
  bool get hasPermission => _hasPermission;
  
  LocationService(this._authService);
  
  @override
  void dispose() {
    _isDisposed = true;
    _locationTimer?.cancel();
    _retryTimer?.cancel();
    super.dispose();
  }
  
  void _safeNotify() {
    if (!_isDisposed) {
      notifyListeners();
    }
  }
  
  Future<bool> checkPermission() async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      print('Location service disabled');
      return false;
    }
    
    LocationPermission permission = await Geolocator.checkPermission();
    
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        print('Location permission denied');
        return false;
      }
    }
    
    if (permission == LocationPermission.deniedForever) {
      print('Location permission denied forever');
      return false;
    }
    
    _hasPermission = true;
    return true;
  }
  
  Future<void> startTracking() async {
    if (_isTracking) return;
    
    final hasPermission = await checkPermission();
    if (!hasPermission) {
      print('Cannot start tracking: no permission');
      return;
    }
    
    _isTracking = true;
    _safeNotify();
    
    // Get initial position
    try {
      _currentPosition = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      if (_isDisposed) return;
      print('Initial position: ${_currentPosition!.latitude}, ${_currentPosition!.longitude}');
      _safeNotify();
    } catch (e) {
      print('Get initial position error: $e');
    }
    
    // Send location every 30 seconds to reduce database contention
    _locationTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (!_isDisposed) _updateLocation();
    });
    
    // Retry queued locations every 30 seconds
    _retryTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (!_isDisposed) _retryQueuedLocations();
    });
  }
  
  void stopTracking() {
    _locationTimer?.cancel();
    _retryTimer?.cancel();
    _isTracking = false;
    _safeNotify();
  }
  
  Future<void> _updateLocation() async {
    if (_isDisposed || _currentPosition == null || _authService.teamId == null) return;
    
    try {
      final position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      
      if (_isDisposed) return;
      _currentPosition = position;
      
      final success = await _sendLocation(position);
      
      if (_isDisposed) return;
      
      if (success) {
        _locationQueue.clear();
      }
      
      if (!success) {
        // Queue for retry (token will be fresh when retrying)
        _locationQueue.add({
          'lat': position.latitude,
          'lng': position.longitude,
        });
        print('Location queued for retry');
      }
      
      _safeNotify();
    } catch (e) {
      print('Update location error: $e');
    }
  }
  
  Future<bool> _sendLocation(Position position) async {
    if (_isDisposed) return false;
    try {
      // SECURE: JWT token contains team_id and branch_id
      // Payload contains ONLY lat/lng - no team identification
      final payload = {
        'lat': position.latitude,
        'lng': position.longitude,
      };
      
      // requireAuth: true sends JWT token in Authorization header
      await ApiService.post('/api/teams/location', payload, requireAuth: true);
      
      print('GPS sent: ${position.latitude.toStringAsFixed(5)}, ${position.longitude.toStringAsFixed(5)}');
      return true;
    } catch (e) {
      // Handle rate limiting (429)
      if (e.toString().contains('429')) {
        print('GPS throttled: rate limited');
        // Return true to avoid queueing - will retry on next cycle
        return true;
      }
      // Handle auth error (403) - try to refresh team token once
      if (e.toString().contains('403')) {
        print('GPS auth error (403) - attempting token refresh');
        final teamNumber = _authService.teamNumber;
        final branchId = _authService.branchId;
        if (teamNumber != null && branchId != null) {
          final refreshed = await _authService.loginWithTeamNumber(teamNumber, branchId);
          if (refreshed) {
            print('Token refreshed, retrying location update');
            try {
              final payload = {
                'lat': position.latitude,
                'lng': position.longitude,
              };
              await ApiService.post('/api/teams/location', payload, requireAuth: true);
              print('GPS sent after refresh: ${position.latitude.toStringAsFixed(5)}, ${position.longitude.toStringAsFixed(5)}');
              return true;
            } catch (retryError) {
              print('Retry after refresh failed: $retryError');
            }
          }
        }
      }
      print('Send location error: $e');
      return false;
    }
  }
  
  Future<void> _retryQueuedLocations() async {
    if (_isDisposed || _locationQueue.isEmpty) return;
    
    print('Retrying ${_locationQueue.length} queued locations');
    
    final toRetry = List<Map<String, dynamic>>.from(_locationQueue);
    _locationQueue.clear();
    
    for (final location in toRetry) {
      if (_isDisposed) return;
      try {
        // Retry with fresh JWT token
        await ApiService.post('/api/teams/location', location, requireAuth: true);
        print('Retried location sent');
      } catch (e) {
        // Don't re-queue if rate limited
        if (_isDisposed) return;
        if (!e.toString().contains('429')) {
          print('Retry failed, re-queueing');
          _locationQueue.add(location);
        } else {
          print('Retry throttled: rate limited');
        }
      }
    }
  }
}
