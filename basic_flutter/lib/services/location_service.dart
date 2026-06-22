import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'dart:async';
import 'auth_service.dart';

class LocationService extends ChangeNotifier {
  Position? _currentPosition;
  StreamSubscription<Position>? _positionStreamSubscription;
  bool _isTracking = false;
  String? _error;

  Position? get currentPosition => _currentPosition;
  bool get isTracking => _isTracking;
  String? get error => _error;
  bool get hasLocation => _currentPosition != null;

  double? get latitude => _currentPosition?.latitude;
  double? get longitude => _currentPosition?.longitude;
  double? get accuracy => _currentPosition?.accuracy;
  double? get speed => _currentPosition?.speed;
  double? get heading => _currentPosition?.heading;

  Future<bool> requestPermission() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          _error = 'Location permission denied';
          notifyListeners();
          return false;
        }
      }

      if (permission == LocationPermission.deniedForever) {
        _error = 'Location permission permanently denied';
        notifyListeners();
        return false;
      }

      return true;
    } catch (e) {
      _error = 'Error requesting location permission: $e';
      notifyListeners();
      return false;
    }
  }

  Future<bool> startLocationTracking(AuthService authService) async {
    // Request all location permissions including background
    final hasPermission = await requestPermission();
    if (!hasPermission) {
      return false;
    }

    // On Android, request background location permission explicitly
    // This is required for location updates when screen is off
    if (await Geolocator.checkPermission() == LocationPermission.whileInUse) {
      final bgPermission = await Geolocator.requestPermission();
      if (bgPermission != LocationPermission.always) {
        _error = 'Background location permission required for tracking when screen is off';
        notifyListeners();
        print('Warning: Background location permission not granted. Tracking will stop when screen turns off.');
      }
    }

    try {
      // Get initial position
      _currentPosition = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      notifyListeners();

      // Configure location settings for background tracking
      // On Android 10+, background location requires a foreground service
      // The geolocator package handles this automatically when background permission is granted
      LocationSettings locationSettings;
      
      if (defaultTargetPlatform == TargetPlatform.android) {
        locationSettings = AndroidSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 10, // Update every 10 meters to save battery
          forceLocationManager: false,
          intervalDuration: const Duration(seconds: 5),
        );
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        locationSettings = AppleSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 10,
          pauseLocationUpdatesAutomatically: false,
          showBackgroundLocationIndicator: true,
        );
      } else {
        locationSettings = const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 10,
        );
      }

      print('Starting location stream with background tracking enabled...');
      
      _positionStreamSubscription = Geolocator.getPositionStream(
          locationSettings: locationSettings,
        ).listen((Position position) {
          _currentPosition = position;
          _error = null;
          notifyListeners();

          print('Position update: lat=${position.latitude}, lng=${position.longitude}');
          print('Auth check: isAuthenticated=${authService.isAuthenticated}, teamId=${authService.teamId}');
          
          if (authService.isAuthenticated && authService.teamId != null) {
            authService.updateTeamLocation(position.latitude, position.longitude);
          } else {
            print('Skipping location update - not authenticated or no team ID');
          }
        }, onError: (error) {
        _error = 'Location tracking error: $error';
        notifyListeners();
        
        print('Location stream error: $error');
        
        // Auto-restart location tracking after error
        Future.delayed(const Duration(seconds: 10), () {
          if (_isTracking && _positionStreamSubscription == null) {
            print('Restarting location tracking after error...');
            _restartLocationTracking(authService);
          }
        });
      });

      // Add time-based heartbeat updates every 10 seconds for continuous tracking
      // This ensures location is sent even if position hasn't changed significantly
      Timer.periodic(const Duration(seconds: 10), (timer) {
        if (_isTracking && _currentPosition != null && authService.isAuthenticated) {
          print('Heartbeat location update...');
          print('Auth state: isAuthenticated=${authService.isAuthenticated}, teamId=${authService.teamId}');
          authService.updateTeamLocation(
            _currentPosition!.latitude,
            _currentPosition!.longitude,
          );
        }
        
        // Stop timer if tracking stopped
        if (!_isTracking) {
          timer.cancel();
        }
      });
      
      _isTracking = true;
      notifyListeners();
      print('Location tracking started successfully with background support');
      return true;
    } catch (e) {
      _error = 'Error starting location tracking: $e';
      notifyListeners();
      print('Failed to start location tracking: $e');
      return false;
    }
  }

  Future<void> stopLocationTracking() async {
    _positionStreamSubscription?.cancel();
    _positionStreamSubscription = null;
    _isTracking = false;
    notifyListeners();
  }

  Future<void> _restartLocationTracking(AuthService authService) async {
    print('Restarting location tracking...');
    await stopLocationTracking();
    await Future.delayed(const Duration(seconds: 2));
    await startLocationTracking(authService);
  }

  // Add heartbeat mechanism for continuous operation
  void startHeartbeat(AuthService authService) {
    // Send periodic heartbeat updates even if position doesn't change
    Timer.periodic(const Duration(minutes: 2), (timer) {
      if (_isTracking && _currentPosition != null && authService.isAuthenticated) {
        print('Sending heartbeat location update...');
        print('Heartbeat auth check: isAuthenticated=${authService.isAuthenticated}, teamId=${authService.teamId}');
        authService.updateTeamLocation(
          _currentPosition!.latitude,
          _currentPosition!.longitude,
        );
      }
    });
  }

  Future<Position?> getCurrentLocation() async {
    try {
      final hasPermission = await requestPermission();
      if (!hasPermission) {
        return null;
      }

      _currentPosition = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      notifyListeners();
      return _currentPosition;
    } catch (e) {
      _error = 'Error getting current location: $e';
      notifyListeners();
      return null;
    }
  }

  double calculateDistance(double startLatitude, double startLongitude, 
                          double endLatitude, double endLongitude) {
    return Geolocator.distanceBetween(
      startLatitude, startLongitude,
      endLatitude, endLongitude,
    );
  }

  @override
  void dispose() {
    _positionStreamSubscription?.cancel();
    super.dispose();
  }
}
