import 'dart:async';
import 'package:flutter/material.dart';
import 'api_service.dart';

class Poi {
  final int id;
  final String? name;
  final String category;
  final double lat;
  final double lng;
  final String? address;

  Poi({
    required this.id,
    required this.name,
    required this.category,
    required this.lat,
    required this.lng,
    this.address,
  });

  factory Poi.fromJson(Map<String, dynamic> json) {
    return Poi(
      id: (json['id'] ?? 0) is int ? json['id'] : int.tryParse('${json['id']}') ?? 0,
      name: json['name'],
      category: json['category'] ?? '',
      lat: (json['lat'] ?? 0.0).toDouble(),
      lng: (json['lng'] ?? 0.0).toDouble(),
      address: json['address'],
    );
  }
}

const List<String> kPoiCategories = [
  'hospital',
  'clinic',
  'doctors',
  'pharmacy',
  'police',
  'fire_station',
  'school',
  'university',
  'kindergarten',
  'bank',
  'fuel',
];

const Map<String, String> kPoiCategoryLabels = {
  'hospital': 'Hospitals',
  'clinic': 'Clinics',
  'doctors': 'Doctors',
  'pharmacy': 'Pharmacies',
  'police': 'Police',
  'fire_station': 'Fire',
  'school': 'Schools',
  'university': 'Universities',
  'kindergarten': 'Kindergartens',
  'bank': 'Banks',
  'fuel': 'Fuel',
};

const Map<String, Color> kPoiCategoryColors = {
  'hospital': Color(0xFFE53935),
  'clinic': Color(0xFFFB8C00),
  'doctors': Color(0xFF00897B),
  'pharmacy': Color(0xFF43A047),
  'police': Color(0xFF1E88E5),
  'fire_station': Color(0xFFD84315),
  'school': Color(0xFF8E24AA),
  'university': Color(0xFF3949AB),
  'kindergarten': Color(0xFFF06292),
  'bank': Color(0xFF6D4C41),
  'fuel': Color(0xFF546E7A),
};

Color poiCategoryColor(String category) {
  return kPoiCategoryColors[category] ?? Colors.grey;
}

String poiCategoryLabel(String category) {
  return kPoiCategoryLabels[category] ?? category;
}

class PoiService with ChangeNotifier {
  List<Poi> _pois = [];
  final Set<String> _hiddenCategories = {};
  bool _isLoading = false;
  bool _isOffline = false;
  Timer? _refreshTimer;

  List<Poi> get pois => _pois;
  bool get isLoading => _isLoading;
  bool get isOffline => _isOffline;

  PoiService() {
    startAutoRefresh();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  void startAutoRefresh() {
    fetchPois();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      fetchPois();
    });
  }

  Future<void> fetchPois() async {
    if (_isLoading) return;

    _isLoading = true;
    notifyListeners();

    try {
      final response = await ApiService.get('/api/pois', requireAuth: true);
      final poisList = response as List;
      _pois = poisList.map((p) => Poi.fromJson(p)).toList();
      _isOffline = false;
      print('POIs fetched: ${_pois.length}');
    } catch (e) {
      print('Fetch POIs error: $e');
      _isOffline = true;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  List<Poi> get visiblePois =>
      _pois.where((p) => !_hiddenCategories.contains(p.category)).toList();

  bool isCategoryVisible(String category) => !_hiddenCategories.contains(category);

  void toggleCategory(String category) {
    if (_hiddenCategories.contains(category)) {
      _hiddenCategories.remove(category);
    } else {
      _hiddenCategories.add(category);
    }
    notifyListeners();
  }

  void showAllCategories() {
    _hiddenCategories.clear();
    notifyListeners();
  }
}