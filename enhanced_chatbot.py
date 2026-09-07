#!/usr/bin/env python3
"""
Enhanced Chatbot Module
Integrates cloud LRC helper bot and local medgemma1.5 for medical analysis
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import the modules we created
from medical_ai_integration import MedicalAIIntegration
from file_upload_handler import FileUploadHandler

# Import prompts
from chat_prompts import LRC_HELPER_SYSTEM_PROMPT, MEDICAL_AI_SYSTEM_PROMPT, CLOUD_MODEL_ROUTING_PROMPT

logger = logging.getLogger(__name__)

class EnhancedChatbot:
    """Enhanced chatbot with dual-model integration"""
    
    def __init__(self, cloud_api_key: Optional[str] = None, cloud_model: str = "gpt-4"):
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        
        # Initialize local medical AI
        self.medical_ai = MedicalAIIntegration()
        
        # Initialize file upload handler
        self.file_handler = FileUploadHandler()
        
        # Check medical AI availability
        self.medical_ai_available = self.medical_ai.check_model_available()
        logger.info(f"Medical AI available: {self.medical_ai_available}")
    
    def route_query(self, query: str, has_file: bool = False) -> Dict[str, str]:
        """Route query to appropriate model using cloud routing"""
        try:
            # Simple keyword-based routing (in production, use the cloud model)
            medical_keywords = [
                'x-ray', 'xray', 'ct scan', 'mri', 'ultrasound', 'ecg', 'eeg',
                'diagnosis', 'symptom', 'treatment', 'medication', 'prescription',
                'lab result', 'blood test', 'analyze image', 'medical report',
                'chest pain', 'fracture', 'tumor', 'infection', 'pneumonia'
            ]
            
            query_lower = query.lower()
            
            # If file is uploaded, route to medical AI
            if has_file:
                return {
                    'route': 'medical_ai',
                    'reasoning': 'File upload detected - requires medical analysis',
                    'priority': 'high'
                }
            
            # Check for medical keywords
            if any(keyword in query_lower for keyword in medical_keywords):
                return {
                    'route': 'medical_ai',
                    'reasoning': 'Medical terminology detected',
                    'priority': 'high'
                }
            
            # Default to LRC helper
            return {
                'route': 'lrc_helper',
                'reasoning': 'General emergency intelligence query',
                'priority': 'medium'
            }
        
        except Exception as e:
            logger.error(f"Error routing query: {e}")
            return {
                'route': 'lrc_helper',
                'reasoning': 'Routing error - defaulting to LRC helper',
                'priority': 'medium'
            }
    
    def query_lrc_helper(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Query the cloud LRC helper bot"""
        try:
            # In production, integrate with cloud API (OpenAI, Anthropic, etc.)
            # For now, return a simulated response
            
            context = context or {}
            
            # Simple keyword-based responses (temporary)
            message_lower = message.lower()
            
            if 'weather' in message_lower:
                return {
                    'success': True,
                    'response': "I can help you with weather information. Our system provides real-time weather data for Libyan cities. Would you like me to check current conditions for a specific location?",
                    'model': 'lrc-helper-cloud',
                    'route': 'lrc_helper'
                }
            elif 'danger' in message_lower or 'risk' in message_lower:
                return {
                    'success': True,
                    'response': "I can provide danger assessment based on multiple data sources including weather patterns, news analysis, and historical incident data. Our AI system evaluates risks and provides recommendations for emergency response teams.",
                    'model': 'lrc-helper-cloud',
                    'route': 'lrc_helper'
                }
            elif 'help' in message_lower:
                return {
                    'success': True,
                    'response': "I'm the LRC Emergency Intelligence System Assistant. I can help with:\n\n• Weather monitoring and analysis\n• Marine and coastal safety data\n• Danger assessment and risk evaluation\n• Team and resource coordination\n• Emergency response planning\n• Medical image analysis (via Medical AI)\n\nHow can I assist you today?",
                    'model': 'lrc-helper-cloud',
                    'route': 'lrc_helper'
                }
            else:
                return {
                    'success': True,
                    'response': "I'm here to help with the LRC Emergency Intelligence System. I can provide information about weather conditions, marine safety, danger assessments, and coordinate emergency response efforts. For medical image analysis, please upload the image and I'll route it to our Medical AI assistant.",
                    'model': 'lrc-helper-cloud',
                    'route': 'lrc_helper'
                }
        
        except Exception as e:
            logger.error(f"Error querying LRC helper: {e}")
            return {
                'success': False,
                'error': str(e),
                'route': 'lrc_helper'
            }
    
    def query_medical_ai(self, message: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Query the local medgemma1.5 model"""
        try:
            if not self.medical_ai_available:
                return {
                    'success': False,
                    'error': 'Medical AI model not available. Please ensure medgemma1.5 is installed in Ollama.',
                    'route': 'medical_ai'
                }
            
            if image_path:
                # Analyze image
                result = self.medical_ai.analyze_image(image_path, message)
                result['route'] = 'medical_ai'
                return result
            else:
                # Analyze text
                result = self.medical_ai.analyze_text(message)
                result['route'] = 'medical_ai'
                return result
        
        except Exception as e:
            logger.error(f"Error querying medical AI: {e}")
            return {
                'success': False,
                'error': str(e),
                'route': 'medical_ai'
            }
    
    def process_message(self, message: str, file: Optional[Any] = None, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Process a message with routing to appropriate model"""
        try:
            # Handle file upload if provided
            image_path = None
            if file:
                upload_result = self.file_handler.save_uploaded_file(file)
                if upload_result['success']:
                    image_path = upload_result['file_path']
                    logger.info(f"File uploaded: {image_path}")
                else:
                    return {
                        'success': False,
                        'error': f"File upload failed: {upload_result['error']}"
                    }
            
            # Route the query
            routing = self.route_query(message, has_file=(image_path is not None))
            logger.info(f"Query routed to: {routing['route']} - {routing['reasoning']}")
            
            # Call appropriate model
            if routing['route'] == 'medical_ai':
                result = self.query_medical_ai(message, image_path)
            else:
                result = self.query_lrc_helper(message, context)
            
            # Add routing info to result
            result['routing'] = routing
            result['timestamp'] = datetime.now().isoformat()
            
            return result
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get status of both models"""
        return {
            'medical_ai': {
                'available': self.medical_ai_available,
                'model': 'medgemma1.5:latest',
                'info': self.medical_ai.get_model_info() if self.medical_ai_available else None
            },
            'lrc_helper': {
                'available': True,  # Always available (cloud)
                'model': self.cloud_model,
                'api_configured': bool(self.cloud_api_key)
            },
            'file_upload': {
                'upload_dir': self.file_handler.upload_dir,
                'max_file_size': self.file_handler.MAX_FILE_SIZE,
                'allowed_extensions': self.file_handler.ALLOWED_EXTENSIONS
            }
        }


# Test the enhanced chatbot
if __name__ == '__main__':
    chatbot = EnhancedChatbot()
    
    print("System Status:")
    status = chatbot.get_system_status()
    print(json.dumps(status, indent=2))
    
    print("\n--- Test LRC Helper ---")
    result = chatbot.process_message("What's the weather in Tripoli?")
    print(json.dumps(result, indent=2))
    
    print("\n--- Test Medical AI Routing ---")
    result = chatbot.process_message("Can you analyze this chest X-ray?")
    print(json.dumps(result, indent=2))
