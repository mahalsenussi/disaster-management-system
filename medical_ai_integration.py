#!/usr/bin/env python3
"""
Medical AI Integration Module
Integrates with local Ollama medgemma1.5 model for medical image analysis
"""

import os
import base64
import json
import requests
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class MedicalAIIntegration:
    """Integration with local Ollama medgemma1.5 model for medical analysis"""
    
    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host
        self.model = "medgemma1.5:latest"
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for medical AI"""
        return """You are a specialized Medical AI Assistant for the Libyan Red Crescent. Your role is to provide medical analysis and support for emergency medical situations.

## Critical Guidelines:
- **ALWAYS Include Disclaimer**: Never provide definitive medical advice without appropriate disclaimers
- **Recommend Verification**: Always recommend verification with qualified medical personnel
- **Prioritize Life-Threatening Conditions**: Flag urgent findings immediately
- **Use Standard Medical Terminology**: Employ proper medical terminology while explaining clearly
- **Consider Resource Constraints**: Take into account available medical resources in Libya

## Response Format:
1. **Disclaimer**: Start with appropriate medical disclaimer
2. **Key Findings**: Highlight critical findings first
3. **Detailed Analysis**: Provide thorough analysis of images/reports
4. **Recommendations**: Suggest next steps and considerations
5. **Urgency Level**: Indicate urgency of findings (LOW/MEDIUM/HIGH/CRITICAL)
6. **Follow-up Required**: Specify what follow-up is needed

## Image Analysis Protocol:
- Describe what you see in the image
- Identify any abnormalities
- Compare with normal findings
- Suggest possible diagnoses
- Recommend additional imaging or tests if needed
- Indicate urgency level

You are a knowledgeable, careful medical assistant dedicated to supporting LRC medical teams with accurate, timely medical insights while always prioritizing patient safety and recommending professional medical verification."""
    
    def analyze_image(self, image_path: str, question: str = "") -> Dict[str, Any]:
        """Analyze a medical image using medgemma1.5"""
        try:
            # Check if file exists
            if not os.path.exists(image_path):
                return {
                    'success': False,
                    'error': f'Image file not found: {image_path}'
                }
            
            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Prepare prompt
            prompt = question if question else "Please analyze this medical image. Describe what you see, identify any abnormalities, and provide your assessment."
            
            # Call Ollama API
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False,
                    "system": self.system_prompt
                },
                timeout=120  # 2 minute timeout for image analysis
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'response': result.get('response', ''),
                    'model': self.model,
                    'image_path': image_path
                }
            else:
                return {
                    'success': False,
                    'error': f'Ollama API error: {response.status_code} - {response.text}'
                }
        
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Request timeout - image analysis took too long'
            }
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def analyze_text(self, text: str, context: str = "") -> Dict[str, Any]:
        """Analyze medical text/reports using medgemma1.5"""
        try:
            prompt = f"{context}\n\n{text}" if context else text
            
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "system": self.system_prompt
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'response': result.get('response', ''),
                    'model': self.model
                }
            else:
                return {
                    'success': False,
                    'error': f'Ollama API error: {response.status_code} - {response.text}'
                }
        
        except Exception as e:
            logger.error(f"Error analyzing text: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_model_available(self) -> bool:
        """Check if medgemma1.5 model is available"""
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                for m in models:
                    model_name = m.get('name', '')
                    # Check for exact match or with :latest tag
                    if model_name == self.model or model_name == 'medgemma1.5:latest' or model_name.startswith('medgemma1.5'):
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking model availability: {e}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the model"""
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                for m in models:
                    model_name = m.get('name', '')
                    if model_name == self.model or model_name == 'medgemma1.5:latest' or model_name.startswith('medgemma1.5'):
                        return {
                            'available': True,
                            'name': m.get('name'),
                            'size': m.get('size'),
                            'modified': m.get('modified_at')
                        }
            return {'available': False}
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {'available': False, 'error': str(e)}


# Test the integration
if __name__ == '__main__':
    medical_ai = MedicalAIIntegration()
    
    print("Checking medgemma1.5 availability...")
    info = medical_ai.get_model_info()
    print(f"Model info: {info}")
    
    if info.get('available'):
        print("\nModel is available!")
        
        # Test text analysis
        print("\nTesting text analysis...")
        result = medical_ai.analyze_text("Patient presents with chest pain and shortness of breath. Vital signs: BP 140/90, HR 95, Temp 37.5°C")
        print(f"Result: {result}")
    else:
        print("Model not available. Please run: ollama pull medgemma1.5")
