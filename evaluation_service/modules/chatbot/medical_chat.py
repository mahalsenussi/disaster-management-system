"""
Medical chatbot using medgemma1.5
"""
import requests
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class MedicalChatbot:
    """Medical chatbot using medical-focused LLM"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "medgemma1.5:latest"
    
    def respond(self, message: str) -> tuple[bool, str]:
        """Get response from medical chatbot
        
        Returns:
            (success, response_text)
        """
        try:
            # Add medical context to prompt
            medical_prompt = f"""You are a medical assistant for disaster response. Provide helpful medical information and guidance.
            
User question: {message}

Provide a helpful and accurate medical response."""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": medical_prompt,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get('response', '')
            
            logger.ai_call(self.model, len(medical_prompt))
            
            return True, response_text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Medical chatbot request failed: {e}", module='MEDICAL_CHATBOT')
            return False, f"Failed to get response: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error in medical chatbot: {e}", module='MEDICAL_CHATBOT', exc_info=True)
            return False, f"Unexpected error: {str(e)}"
    
    def respond_async(self, message: str) -> str:
        """Get response asynchronously (for queue processing)"""
        success, response = self.respond(message)
        return response if success else "I'm sorry, I couldn't process your medical request."
