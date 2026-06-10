# Libya Disaster Management Mobile App

A Flutter mobile application for disaster management teams in Libya. This app integrates with the disaster management system to provide real-time team tracking, incident assignment, and routing capabilities.

## 🎯 Key Features

### Team Management
- **Team Login**: Login using team number or QR code authentication
- **Real-time GPS Tracking**: Automatic location updates to the central system
- **Team Status Management**: Update team availability and status

### Incident Management
- **Active Incidents**: View all active disasters and emergencies
- **Accept Assignments**: Accept incidents assigned by operators
- **Route Navigation**: Get real-time routes to incident locations using OSRM

### Map Integration
- **Live Location**: Show current team location on map
- **Route Visualization**: Display calculated routes with turn-by-turn directions
- **Libya-specific Routing**: Uses real OpenStreetMap/OSRM data for accurate routing

### API Integration
- **Real-time Data**: Connects to `https://info.onlineacademy.com.ly/api`
- **Secure Authentication**: Token-based authentication for team access
- **Location Updates**: Automatic GPS position updates to central system

## 🚀 Getting Started

### Prerequisites

- Flutter SDK 3.0.0 or higher
- Dart SDK 2.17.0 or higher
- Android Studio or Xcode for mobile development
- API access to the disaster management system

### Installation

1. **Clone and navigate to the project:**
   ```bash
   cd /var/www/html/info/basic_flutter
   ```

2. **Install dependencies:**
   ```bash
   flutter pub get
   ```

3. **Run the app:**
   ```bash
   # For Android
   flutter run

   # For iOS (requires macOS and Xcode)
   flutter run -d ios
   ```

### Building for Production

```bash
# Android APK
flutter build apk --release

# Android App Bundle
flutter build appbundle --release

# iOS (requires macOS and Apple Developer account)
flutter build ios --release
```

## 📱 App Structure

### Screens
- **Login Screen**: Team authentication with QR code or team number
- **Home Screen**: Dashboard with team status, location, and incident summary
- **Map Screen**: Interactive map with current location and routes
- **Incident Screen**: List of assigned incidents with route navigation

### Services
- **AuthService**: Team authentication and session management
- **LocationService**: GPS tracking and location updates
- **ApiService**: HTTP communication with disaster management API

### API Endpoints
The app communicates with the following API endpoints:

- `POST /api/team/login` - Team login with team number
- `POST /api/team/qr-login` - QR code authentication
- `POST /api/team/update-location` - Update team GPS location
- `GET /api/disasters?status=active` - Get active incidents
- `GET /api/team/{id}/assignments` - Get team assignments
- `POST /api/libya-route` - Calculate route to incident
- `POST /api/team/{id}/accept-incident` - Accept incident assignment

## 🗺️ Libya Routing System

The app uses the advanced Libya routing system integrated with:
- **Real OSRM Data**: OpenStreetMap routing for accurate road networks
- **City Names**: Support for both Arabic and English city names
- **Multiple Formats**: Coordinates (lat,lng) or city names
- **Real-time Updates**: Live route calculation based on current location

### Supported Cities
- Tripoli (طرابلس)
- Benghazi (بنغازي)
- Misrata (مصراتة)
- Sirte (سرت)
- Sabha (سبها)
- And 12 more Libyan cities...

## 🔧 Configuration

### API Base URL
The app is configured to connect to:
```dart
static const String baseUrl = 'https://info.onlineacademy.com.ly';
```

### Location Tracking
- **Update Interval**: Every 10 seconds or 10 meters movement
- **Accuracy**: High precision GPS
- **Background Updates**: Automatic location updates while app is active

## 🎨 UI/UX Features

### Arabic Interface
- Fully localized Arabic UI
- RTL (Right-to-Left) layout support
- Arabic labels and notifications

### Real-time Updates
- Live team location on map
- Real-time incident notifications
- Automatic data refresh

### Responsive Design
- Works on various screen sizes
- Mobile-optimized interface
- Adaptive layouts for tablets

## 🔒 Security Features

- Token-based authentication
- Secure API communication (HTTPS)
- Local credential storage with encryption
- Session management and auto-logout

## 🧪 Testing

### Unit Tests
```bash
flutter test
```

### Integration Tests
```bash
flutter drive --target=test_driver/app.dart
```

## 🚀 Deployment

### Android
1. Generate signing key
2. Configure `android/app/build.gradle`
3. Build release APK: `flutter build apk --release`

### iOS
1. Configure signing in Xcode
2. Set up provisioning profile
3. Build release: `flutter build ios --release`

## 📞 Support

For technical support or questions about the mobile app integration:
- API Base: `https://info.onlineacademy.com.ly`
- Contact: Development Team

## 📄 License

This project is part of the Libya Disaster Management System.

## 🙏 Acknowledgments

- OpenStreetMap contributors for map data
- OSRM project for routing engine
- Flutter team for the excellent framework

---

**Built with ❤️ for Libya Emergency Response**
