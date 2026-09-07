"""
Coastal data evaluator using Ollama LLM
"""
import os
import requests
from typing import Dict, Optional, Tuple
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.core.ollama import resolve_models

logger = get_logger()
cache = get_cache()

class CoastalEvaluator:
    """Evaluates coastal data using Ollama LLM"""
    
    def __init__(self, ollama_url: str = None):
        self.ollama_url = ollama_url or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        self.cloud_model = os.environ.get('OLLAMA_MODEL', 'minimax-m3:cloud')
        self.local_model = os.environ.get('OLLAMA_MODEL', 'minimax-m2.1:cloud')
        self.models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)
        if self.models:
            logger.info(f"Resolved Ollama models: {self.models}", module='COASTAL_EVALUATOR')
    
    def evaluate_cloud(self, coastal_data: Dict) -> Tuple[bool, Optional[float], Optional[str]]:
        """Evaluate coastal data using cloud model (real-time)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(coastal_data, self.models)
    
    def evaluate_local(self, coastal_data: Dict) -> Tuple[bool, Optional[float], Optional[str]]:
        """Evaluate coastal data using local model (fallback)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(coastal_data, self.models[::-1])
    
    def _evaluate(self, coastal_data: Dict, models: list) -> Tuple[bool, Optional[float], Optional[str]]:
        """Evaluate coastal data trying each model in order"""
        if not models:
            models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)

        prompt = self._build_prompt(coastal_data)
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
                logger.info(f"Evaluation completed for {coastal_data.get('location')} with {model}", module='COASTAL_EVALUATOR')
                return True, risk_score, evaluation_text

            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed: {e}", module='COASTAL_EVALUATOR')

        logger.error(f"All coastal evaluation models failed: {last_error}", module='COASTAL_EVALUATOR')
        return False, None, None
    
    def evaluate(self, coastal_data: Dict) -> Tuple[bool, Optional[float], Optional[str]]:
        """Evaluate coastal data with fallback mechanism
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        # Try cloud model first
        success, risk_score, evaluation = self.evaluate_cloud(coastal_data)
        
        if success:
            return success, risk_score, evaluation
        
        # Fall back to local model
        logger.warning("Cloud evaluation failed, falling back to local model", module='COASTAL_EVALUATOR')
        success, risk_score, evaluation = self.evaluate_local(coastal_data)
        
        if success:
            return success, risk_score, evaluation
        
        logger.error("Both cloud and local evaluation failed", module='COASTAL_EVALUATOR')
        return False, None, None
    
    def _build_prompt(self, coastal_data: Dict) -> str:
        """Build evaluation prompt for coastal data"""
        location = coastal_data.get('location', 'Unknown')
        wave_height = coastal_data.get('wave_height', 0)
        wave_period = coastal_data.get('wave_period', 0)
        sea_level_anomaly = coastal_data.get('sea_level_anomaly', 0)
        wind_speed = coastal_data.get('wind_speed', 0)
        
        prompt = f"""You are a disaster risk assessment expert for coastal areas. Analyze the following coastal data for {location} and provide a disaster risk assessment.

Coastal Data:
- Location: {location}
- Wave Height: {wave_height} meters
- Wave Period: {wave_period} seconds
- Sea Level Anomaly: {sea_level_anomaly} meters
- Wind Speed: {wind_speed} m/s

Please provide:
1. A risk score between 0.0 (no risk) and 1.0 (extreme risk)
2. A detailed explanation of the risk factors
3. Specific recommendations for safety measures

Format your response as:
Risk Score: [0.0-1.0]
Explanation: [Your detailed analysis]
"""
        return prompt
    
    def _parse_risk_score(self, evaluation_text: str) -> Optional[float]:
        """Parse risk score from evaluation text"""
        try:
            # Look for "Risk Score: X.XX" pattern
            import re
            match = re.search(r'Risk Score:\s*([0-9.]+)', evaluation_text)
            if match:
                score = float(match.group(1))
                # Ensure score is between 0 and 1
                return max(0.0, min(1.0, score))
        except:
            pass
        
        # Default to moderate risk if parsing fails
        return 0.5
