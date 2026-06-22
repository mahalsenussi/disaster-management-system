import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

class QRScannerWidget extends StatefulWidget {
  final Function(String) onQRCodeScanned;

  const QRScannerWidget({
    super.key,
    required this.onQRCodeScanned,
  });

  @override
  State<QRScannerWidget> createState() => _QRScannerWidgetState();
}

class _QRScannerWidgetState extends State<QRScannerWidget> {
  final TextEditingController _qrController = TextEditingController();

  @override
  void dispose() {
    _qrController.dispose();
    super.dispose();
  }

  void _scanQRCode() {
    if (_qrController.text.trim().isNotEmpty) {
      widget.onQRCodeScanned(_qrController.text.trim());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // QR Code Scanner Simulation
        Expanded(
          child: Container(
            margin: const EdgeInsets.all(16.0),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.blue.shade800, width: 2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.qr_code_scanner,
                  size: 80,
                  color: Colors.blue.shade800,
                ),
                const SizedBox(height: 16),
                const Text(
                  'محاكاة ماسح QR',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'في التطبيق الحقيقي، سيستخدم الكاميرا\nلقراءة كود QR',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey),
                ),
                const SizedBox(height: 24),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                  child: TextField(
                    controller: _qrController,
                    decoration: InputDecoration(
                      labelText: 'أدخل كود QR (محاكاة)',
                      hintText: 'مثال: TEAM001:VERIFY123',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      prefixIcon: const Icon(Icons.qr_code),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _scanQRCode,
                  icon: const Icon(Icons.check),
                  label: const Text('تأكيد الكود'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue.shade800,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
                  ),
                ),
              ],
            ),
          ),
        ),
        // Generate QR Code Section
        Container(
          padding: const EdgeInsets.all(16.0),
          decoration: BoxDecoration(
            color: Colors.grey.shade100,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              const Text(
                'مثال على كود QR للفريق',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              QrImageView(
                data: 'TEAM001:VERIFY123',
                version: QrVersions.auto,
                size: 150.0,
                backgroundColor: Colors.white,
              ),
              const SizedBox(height: 8),
              Text(
                'TEAM001:VERIFY123',
                style: TextStyle(
                  color: Colors.grey.shade600,
                  fontFamily: 'monospace',
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
