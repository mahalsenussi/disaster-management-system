"""
General chatbot using lrc-assistant and kimi-k2.5
"""
import requests
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class GeneralChatbot:
    """General chatbot using Llama models"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.primary_model = "lrc-assistant:latest"
        self.fallback_model = "kimi-k2.5"
    
    def respond(self, message: str, use_fallback: bool = False) -> tuple[bool, str]:
        """Get response from chatbot
        
        Returns:
            (success, response_text)
        """
        model = self.fallback_model if use_fallback else self.primary_model
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": message,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get('response', '')
            
            logger.ai_call(model, len(message))
            
            return True, response_text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Chatbot request failed: {e}", module='GENERAL_CHATBOT')
            
            # Try fallback if primary failed
            if not use_fallback:
                logger.warning(f"Primary model failed, trying fallback: {self.fallback_model}", module='GENERAL_CHATBOT')
                return self.respond(message, use_fallback=True)
            
            return False, f"Failed to get response: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error in chatbot: {e}", module='GENERAL_CHATBOT', exc_info=True)
            return False, f"Unexpected error: {str(e)}"
    
    def respond_async(self, message: str) -> str:
        """Get response asynchronously (for queue processing)"""
        success, response = self.respond(message)
        return response if success else "I'm sorry, I couldn't process your request."
