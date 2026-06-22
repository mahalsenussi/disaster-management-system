import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../widgets/qr_scanner.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _teamNumberController = TextEditingController();
  bool _isLoading = false;
  String? _errorMessage;
  bool _showQRScanner = false;

  @override
  void dispose() {
    _teamNumberController.dispose();
    super.dispose();
  }

  Future<void> _loginWithTeamNumber() async {
    if (_teamNumberController.text.trim().isEmpty) {
      setState(() {
        _errorMessage = 'الرجاء إدخال رقم الفريق';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final authService = Provider.of<AuthService>(context, listen: false);
    final success = await authService.loginWithTeamNumber(
      _teamNumberController.text.trim(),
    );

    setState(() {
      _isLoading = false;
    });

    if (!success) {
      setState(() {
        _errorMessage = 'فشل تسجيل الدخول. الرجاء التحقق من رقم الفريق.';
      });
    }
  }

  void _onQRCodeScanned(String qrData) {
    setState(() {
      _showQRScanner = false;
      _isLoading = true;
      _errorMessage = null;
    });

    final authService = Provider.of<AuthService>(context, listen: false);
    authService.loginWithQRCode(qrData).then((success) {
      setState(() {
        _isLoading = false;
      });

      if (!success) {
        setState(() {
          _errorMessage = 'فشل تسجيل الدخول بالكود QR. الرجاء المحاولة مرة أخرى.';
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Colors.blue.shade800,
              Colors.blue.shade600,
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // App Logo
                  Icon(
                    Icons.local_fire_department,
                    size: 80,
                    color: Colors.white,
                  ),
                  const SizedBox(height: 16),
                  
                  // App Title
                  Text(
                    'نظام إدارة الكوارث',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'ليبيا - Libya Disaster Management',
                    style: TextStyle(
                      fontSize: 16,
                      color: Colors.white70,
                    ),
                  ),
                  const SizedBox(height: 40),

                  if (_showQRScanner) ...[
                    // QR Scanner
                    Container(
                      height: 300,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: QRScannerWidget(
                        onQRCodeScanned: _onQRCodeScanned,
                      ),
                    ),
                    const SizedBox(height: 16),
                    ElevatedButton.icon(
                      onPressed: () {
                        setState(() {
                          _showQRScanner = false;
                        });
                      },
                      icon: const Icon(Icons.arrow_back),
                      label: const Text('العودة للخلف'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: Colors.blue.shade800,
                      ),
                    ),
                  ] else ...[
                    // Login Card
                    Container(
                      padding: const EdgeInsets.all(24.0),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.2),
                            blurRadius: 10,
                            offset: const Offset(0, 5),
                          ),
                        ],
                      ),
                      child: Column(
                        children: [
                          Text(
                            'تسجيل دخول الفريق',
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.bold,
                              color: Colors.blue.shade800,
                            ),
                          ),
                          const SizedBox(height: 24),

                          // Team Number Input
                          TextField(
                            controller: _teamNumberController,
                            keyboardType: TextInputType.number,
                            decoration: InputDecoration(
                              labelText: 'رقم الفريق',
                              hintText: 'أدخل رقم الفريق',
                              prefixIcon: const Icon(Icons.group),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                          ),
                          const SizedBox(height: 16),

                          // Error Message
                          if (_errorMessage != null)
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.red.shade50,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.red.shade200),
                              ),
                              child: Row(
                                children: [
                                  Icon(Icons.error, color: Colors.red.shade600),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      _errorMessage!,
                                      style: TextStyle(color: Colors.red.shade600),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          if (_errorMessage != null) const SizedBox(height: 16),

                          // Login Button
                          SizedBox(
                            width: double.infinity,
                            height: 50,
                            child: ElevatedButton(
                              onPressed: _isLoading ? null : _loginWithTeamNumber,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.blue.shade800,
                                foregroundColor: Colors.white,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              child: _isLoading
                                  ? const CircularProgressIndicator(color: Colors.white)
                                  : const Text(
                                      'تسجيل الدخول',
                                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                                    ),
                            ),
                          ),
                          const SizedBox(height: 16),

                          // Divider
                          Row(
                            children: [
                              Expanded(child: Divider(color: Colors.grey.shade300)),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 16),
                                child: Text(
                                  'أو',
                                  style: TextStyle(color: Colors.grey.shade600),
                                ),
                              ),
                              Expanded(child: Divider(color: Colors.grey.shade300)),
                            ],
                          ),
                          const SizedBox(height: 16),

                          // QR Code Login Button
                          SizedBox(
                            width: double.infinity,
                            height: 50,
                            child: OutlinedButton.icon(
                              onPressed: () {
                                setState(() {
                                  _showQRScanner = true;
                                });
                              },
                              icon: const Icon(Icons.qr_code_scanner),
                              label: const Text('تسجيل الدخول بكود QR'),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: Colors.blue.shade800,
                                side: BorderSide(color: Colors.blue.shade800),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
