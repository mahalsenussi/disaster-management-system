"""
Shared authentication for evaluation service
Validates tokens from operation system
"""
import os
import hmac
import hashlib
from datetime import datetime, timedelta
import jwt

class AuthValidator:
    """Validates tokens from operation system"""
    
    def __init__(self, secret_key=None):
        self.secret_key = secret_key or os.environ.get('EVALUATION_SECRET_KEY', 'evaluation-secret-key-change-in-production')
    
    def generate_token(self, user_id: str, expires_in: int = 3600) -> str:
        """Generate a token (for testing purposes)"""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def validate_token(self, token: str) -> dict:
        """Validate token and return payload"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return {'valid': True, 'payload': payload}
        except jwt.ExpiredSignatureError:
            return {'valid': False, 'error': 'Token expired'}
        except jwt.InvalidTokenError:
            return {'valid': False, 'error': 'Invalid token'}
    
    def validate_request(self, request) -> dict:
        """Validate token from request headers"""
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return {'valid': False, 'error': 'No authorization header'}
        
        if not auth_header.startswith('Bearer '):
            return {'valid': False, 'error': 'Invalid authorization format'}
        
        token = auth_header.split(' ')[1]
        return self.validate_token(token)

# Global auth validator instance
_auth_validator = None

def get_auth_validator():
    """Get global auth validator instance"""
    global _auth_validator
    if _auth_validator is None:
        _auth_validator = AuthValidator()
    return _auth_validator
