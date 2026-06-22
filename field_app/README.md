# Emergency Field Operations App

A real-time field operations mobile application for emergency response teams in Libya.

## Features

### Core Functionality
- **Login System**: Team number or QR code authentication with auto-login
- **Live Map**: Real-time map showing teams, incidents, and routes
- **GPS Tracking**: Continuous location updates with queue/retry on network failure
- **Route Navigation**: OSRM-powered routing with automatic rerouting
- **Offline Support**: Works under weak/unstable network conditions
- **Auto Refresh**: Teams and incidents update every 8 seconds

### Advanced Features
- **Automatic Rerouting**: Detects route deviation (>80m) and recalculates
- **Rerouting Cooldown**: 20-second cooldown to prevent infinite reroutes
- **GPS State Indicators**: Color-coded markers (green=active, orange=lost, gray=manual)
- **Incident Severity**: Color-coded by severity (red=high, orange=medium, yellow=low)
- **Info Panel**: Shows incident type, ETA, and distance
- **Offline Mode**: Maintains last data when network fails

## Architecture

### Services
- **AuthService**: Login, logout, auto-login with SharedPreferences
- **TeamService**: Fetch teams, auto-refresh every 8 seconds
- **IncidentService**: Fetch incidents, auto-refresh every 8 seconds
- **RouteService**: Fetch route, check deviation, trigger reroute
- **LocationService**: GPS tracking, location queue, retry logic
- **ApiService**: HTTP client with error handling

### Screens
- **LoginScreen**: Team number input + QR scanner
- **MapScreen**: Live map with all overlays

## API Endpoints

```
GET  /api/teams
GET  /api/incidents
GET  /api/teams/<teamId>/route
POST /api/teams/location
POST /api/routes/recalculate
```

## Configuration

### API Base URL
Set in `lib/services/api_service.dart`:
```dart
static const String baseUrl = 'https://emergency.onlineacademy.com.ly';
```

### Rerouting Threshold
Set in `lib/services/route_service.dart`:
```dart
static const double _rerouteThresholdMeters = 80.0;
static const Duration _rerouteCooldown = Duration(seconds: 20);
```

### Refresh Intervals
- Teams/Incidents: 8 seconds
- Route: 10 seconds
- GPS: 4 seconds
- Location Retry: 10 seconds

## Installation

### Prerequisites
- Flutter SDK 3.0+
- Android SDK 21+

### Setup
```bash
cd field_app
flutter pub get
```

### Build APK
```bash
flutter build apk --debug
```

### Install on Device
```bash
adb install build/app/outputs/flutter-apk/app-debug.apk
```

## Permissions

The app requires:
- **Location**: Fine and coarse location for GPS tracking
- **Camera**: For QR code scanning
- **Internet**: For API communication

## Usage

### Login
1. Enter team number (e.g., "101")
2. Or scan QR code containing team number
3. App auto-saves credentials for next launch

### Map View
- **Blue marker**: Your current location
- **Colored circles**: Other teams (color by GPS state)
- **Warning icons**: Incidents (color by severity)
- **Blue line**: Assigned route
- **Red marker**: Route destination

### Rerouting
- If you deviate >80m from route, automatic reroute triggers
- "Re-routing..." indicator appears during recalculation
- 20-second cooldown between reroutes

### Offline Mode
- Orange "Offline" indicator in app bar when network fails
- Last known data remains visible
- Location updates queued and retried

## Logging

The app logs:
- GPS sent: `GPS sent: lat, lng`
- Route received: `Route updated: {id}`
- API errors: `API Error [endpoint]: {error}`
- Reroute trigger: `Route deviation detected`
- Reroute success: `Reroute successful`

## Performance

- Minimal rebuilds using Provider
- Cached markers
- Efficient map rendering
- Background location updates
- Non-blocking API calls

## Reliability

- Never crashes on API failure
- Maintains last data offline
- Queues failed location updates
- Graceful permission handling
- Network timeout protection (10s)

## Package Name
`com.libya.field_app`

## Dependencies
- flutter_map: ^6.1.0
- latlong2: ^0.9.0
- http: ^1.1.0
- provider: ^6.1.0
- shared_preferences: ^2.2.0
- geolocator: ^10.1.0
- mobile_scanner: ^4.0.0
- permission_handler: ^11.0.0
- intl: ^0.18.0
