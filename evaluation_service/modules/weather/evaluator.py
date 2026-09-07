"""
Weather evaluator using Ollama LLM
"""
import os
import requests
import json
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.core.ollama import resolve_models

logger = get_logger()
cache = get_cache()

class WeatherEvaluator:
    """Evaluates weather data using Ollama LLM"""
    
    def __init__(self, ollama_url: str = None):
        self.ollama_url = ollama_url or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        self.cloud_model = os.environ.get('OLLAMA_MODEL', 'minimax-m3:cloud')
        self.local_model = os.environ.get('OLLAMA_MODEL', 'minimax-m2.1:cloud')
        self.models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)
        if self.models:
            logger.info(f"Resolved Ollama models: {self.models}", module='WEATHER_EVALUATOR')
    
    def evaluate_cloud(self, weather_data: Dict) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate weather data using cloud model (real-time)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(weather_data, self.models)
    
    def evaluate_local(self, weather_data: Dict) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate weather data using local model (background)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(weather_data, self.models[::-1])
    
    def _evaluate(self, weather_data: Dict, models: list) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate weather data trying each model in order"""
        if not models:
            models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)

        prompt = self._build_prompt(weather_data)
        last_error = None

        for model in models:
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=75
                )
                response.raise_for_status()

                result = response.json()
                evaluation_text = result.get('response', '')

                if not evaluation_text:
                    last_error = f"Model {model} returned empty response"
                    continue

                # Parse risk score from evaluation
                risk_score = self._parse_risk_score(evaluation_text)

                logger.ai_call(model, len(prompt))
                return True, risk_score, evaluation_text

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"Model {model} failed: {e}", module='WEATHER_EVALUATOR')
            except Exception as e:
                last_error = e
                logger.warning(f"Unexpected error with model {model}: {e}", module='WEATHER_EVALUATOR')

        logger.error(f"All weather evaluation models failed: {last_error}", module='WEATHER_EVALUATOR')
        return False, None, None
    
    def _build_prompt(self, weather_data: Dict) -> str:
        """Build evaluation prompt"""
        prompt = f"""Evaluate the following weather data for disaster risk:

City: {weather_data.get('city', 'Unknown')}
Temperature: {weather_data.get('temperature', 'N/A')}°C
Humidity: {weather_data.get('humidity', 'N/A')}%
Pressure: {weather_data.get('pressure', 'N/A')} hPa
Wind Speed: {weather_data.get('wind_speed', 'N/A')} m/s

Provide a risk score between 0.0 (no risk) and 1.0 (extreme risk) and a brief explanation.
Format your response as:
Risk Score: [0.0-1.0]
Explanation: [your explanation]"""
        
        return prompt
    
    def _parse_risk_score(self, evaluation_text: str) -> Optional[float]:
        """Parse risk score from evaluation text"""
        try:
            # Look for "Risk Score: X.X" pattern
            for line in evaluation_text.split('\n'):
                if 'Risk Score:' in line.lower():
                    # Extract the number
                    parts = line.split(':')
                    if len(parts) > 1:
                        score_str = parts[1].strip()
                        # Remove any non-numeric characters except decimal point
                        score_str = ''.join(c for c in score_str if c.isdigit() or c == '.')
                        if score_str:
                            return float(score_str)
            
            # If not found in standard format, try to find any number
            import re
            numbers = re.findall(r'\d+\.?\d*', evaluation_text)
            if numbers:
                return float(numbers[0])
            
            return None
        except Exception as e:
            logger.error(f"Failed to parse risk score: {e}", module='WEATHER_EVALUATOR')
            return None
    
    def evaluate_with_fallback(self, weather_data: Dict) -> tuple[bool, float, str]:
        """Evaluate with cloud model, fallback to local if cloud fails"""
        success, risk_score, evaluation = self.evaluate_cloud(weather_data)
        
        if success and risk_score is not None:
            return True, risk_score, evaluation
        
        # Fallback to local model
        logger.warning("Cloud evaluation failed, falling back to local model", module='WEATHER_EVALUATOR')
        success, risk_score, evaluation = self.evaluate_local(weather_data)
        
        if success and risk_score is not None:
            return True, risk_score, evaluation
        
        # If both fail, return default
        logger.error("Both cloud and local evaluation failed", module='WEATHER_EVALUATOR')
        return False, 0.5, "Evaluation failed - using default risk score"
