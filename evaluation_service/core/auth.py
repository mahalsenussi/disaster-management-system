"""
Shared authentication for evaluation service
Validates the SAME tokens issued by the operation/dashboard system:
  - same JWT secret (JWT_SECRET_KEY)
  - same users table (disaster_ops.db) with role + is_active + branch/region
A single dashboard login (e.g. admin/CHANGEME) therefore authorizes both the
main emergency dashboard and the chatbot/evaluation service.
"""
import os
from datetime import datetime, timedelta
import jwt

# Default secret MUST match public_app/auth.py so dashboard tokens validate here.
DEFAULT_JWT_SECRET = 'your-secret-key-change-in-production'
# Shared users database (same file the dashboard login reads).
_DEFAULTS = {
    'database': os.path.join(os.path.dirname(__file__), '..', '..',
                             'public_app', 'database', 'disaster_ops.db'),
}


class AuthValidator:
    """Validates tokens issued by the operation/dashboard system"""

    def __init__(self, secret_key=None, database=None):
        self.secret_key = secret_key or os.environ.get(
            'JWT_SECRET_KEY', DEFAULT_JWT_SECRET)
        # Same secret->same secret_key used by dashboard auth.
        self.database = database or os.environ.get(
            'AUTH_DATABASE') or _DEFAULTS['database']
        # Resolve relative database path relative to this project root
        if not os.path.isabs(self.database):
            root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
            self.database = os.path.join(root, self.database)
        self.database = os.path.normpath(self.database)

    def generate_token(self, user_id: str, expires_in: int = 3600) -> str:
        """Generate a token (for testing / issuing shareable tokens)"""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def _load_user(self, user_id: int) -> dict:
        """Load user (+role, branch, region, active flag) from shared DB"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.database, timeout=20)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                'SELECT id, username, role, branch_id, region, is_active '
                'FROM users WHERE id = ?', (user_id,))
            row = cur.fetchone()
            conn.close()
            return dict(row) if row else {}
        except Exception:
            return {}

    def validate_token(self, token: str) -> dict:
        """Validate token and return payload (+ live user RBAC context)"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            user_id = payload.get('user_id')
            user = self._load_user(user_id) if user_id is not None else {}
            if not user:
                return {'valid': False, 'error': 'User no longer exists'}
            if not user.get('is_active', 1):
                return {'valid': False, 'error': 'User deactivated'}
            payload['role'] = user.get('role')
            payload['branch_id'] = user.get('branch_id')
            payload['region'] = user.get('region')
            payload['username'] = user.get('username')
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


_auth_validator = None


def get_auth_validator():
    """Get global auth validator instance"""
    global _auth_validator
    if _auth_validator is None:
        _auth_validator = AuthValidator()
    return _auth_validator
