#!/usr/bin/env python3
"""
File Upload Handler Module
Handles file uploads for medical reports, X-rays, and other documents
"""

import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

class FileUploadHandler:
    """Handler for file uploads in the chatbot system"""
    
    ALLOWED_EXTENSIONS = {
        'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'dicom'},
        'document': {'pdf', 'doc', 'docx', 'txt', 'rtf'},
        'report': {'pdf', 'txt', 'json', 'csv'}
    }
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
    
    def __init__(self, upload_dir: str = '/tmp/lrc_uploads'):
        self.upload_dir = upload_dir
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """Ensure upload directory exists"""
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir, exist_ok=True)
            logger.info(f"Created upload directory: {self.upload_dir}")
    
    def _get_file_extension(self, filename: str) -> str:
        """Get file extension"""
        return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    def _get_file_type(self, filename: str) -> Optional[str]:
        """Determine file type based on extension"""
        ext = self._get_file_extension(filename)
        
        for file_type, extensions in self.ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        
        return None
    
    def _is_allowed_file(self, filename: str) -> bool:
        """Check if file is allowed"""
        ext = self._get_file_extension(filename)
        return any(ext in extensions for extensions in self.ALLOWED_EXTENSIONS.values())
    
    def save_uploaded_file(self, file, file_type: str = 'auto') -> Dict[str, Any]:
        """Save an uploaded file"""
        try:
            # Check if file was provided
            if not file or not file.filename:
                return {
                    'success': False,
                    'error': 'No file provided'
                }
            
            # Secure filename
            filename = secure_filename(file.filename)
            
            # Check file extension
            if not self._is_allowed_file(filename):
                return {
                    'success': False,
                    'error': f'File type not allowed. Allowed types: {", ".join([ext for exts in self.ALLOWED_EXTENSIONS.values() for ext in exts])}'
                }
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > self.MAX_FILE_SIZE:
                return {
                    'success': False,
                    'error': f'File too large. Maximum size: {self.MAX_FILE_SIZE / (1024*1024):.0f}MB'
                }
            
            # Determine file type
            if file_type == 'auto':
                file_type = self._get_file_type(filename) or 'document'
            
            # Generate unique filename
            unique_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{unique_id}_{filename}"
            
            # Save file
            file_path = os.path.join(self.upload_dir, safe_filename)
            file.save(file_path)
            
            logger.info(f"File saved: {file_path} ({file_size} bytes)")
            
            return {
                'success': True,
                'file_path': file_path,
                'original_filename': filename,
                'file_size': file_size,
                'file_type': file_type,
                'uploaded_at': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File deleted: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """Clean up old files"""
        try:
            current_time = datetime.now()
            deleted_count = 0
            
            for filename in os.listdir(self.upload_dir):
                file_path = os.path.join(self.upload_dir, filename)
                
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    age_hours = (current_time - file_time).total_seconds() / 3600
                    
                    if age_hours > max_age_hours:
                        if self.delete_file(file_path):
                            deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old files")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
            return 0
    
    def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get information about a file"""
        try:
            if not os.path.exists(file_path):
                return None
            
            stat = os.stat(file_path)
            return {
                'path': file_path,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'extension': self._get_file_extension(file_path),
                'file_type': self._get_file_type(file_path)
            }
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None


# Test the handler
if __name__ == '__main__':
    handler = FileUploadHandler()
    print(f"Upload directory: {handler.upload_dir}")
    print(f"Allowed extensions: {handler.ALLOWED_EXTENSIONS}")
    print(f"Max file size: {handler.MAX_FILE_SIZE / (1024*1024):.0f}MB")
