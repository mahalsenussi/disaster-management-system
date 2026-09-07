"""
News evaluator using Ollama LLM
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

class NewsEvaluator:
    """Evaluates news data using Ollama LLM"""
    
    def __init__(self, ollama_url: str = None):
        self.ollama_url = ollama_url or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        self.cloud_model = os.environ.get('OLLAMA_MODEL', 'minimax-m3:cloud')
        self.local_model = os.environ.get('OLLAMA_MODEL', 'minimax-m2.1:cloud')
        self.models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)
        if self.models:
            logger.info(f"Resolved Ollama models: {self.models}", module='NEWS_EVALUATOR')
    
    def evaluate_cloud(self, news_data: Dict) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate news data using cloud model (real-time)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(news_data, self.models)

    def evaluate_local(self, news_data: Dict) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate news data using local model (background)
        
        Returns:
            (success, risk_score, evaluation_text)
        """
        return self._evaluate(news_data, self.models[::-1])

    def _evaluate(self, news_data: Dict, models: list) -> tuple[bool, Optional[float], Optional[str]]:
        """Evaluate news data trying each model in order"""
        if not models:
            models = resolve_models(self.ollama_url, preferred=self.cloud_model, fallback=self.local_model)

        prompt = self._build_prompt(news_data)
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
                logger.warning(f"Model {model} failed: {e}", module='NEWS_EVALUATOR')
            except Exception as e:
                last_error = e
                logger.warning(f"Unexpected error with model {model}: {e}", module='NEWS_EVALUATOR')

        logger.error(f"All news evaluation models failed: {last_error}", module='NEWS_EVALUATOR')
        return False, None, None
    
    def _build_prompt(self, news_data: Dict) -> str:
        """Build evaluation prompt with cluster analysis"""
        titles = news_data.get('titles', [])
        summaries = news_data.get('summaries', [])
        
        titles_text = "\n".join(titles[:10]) if titles else "N/A"
        summaries_text = "\n".join(summaries[:10]) if summaries else "N/A"
        
        prompt = f"""Analyze the following news cluster:

Titles:
{titles_text}

Summaries:
{summaries_text}

Tasks:

1. Identify main event type:
   (fire, flood, conflict, explosion, humanitarian, unknown)

2. Identify likely location:
   (city, country, region)

3. Estimate severity (0.0 - 1.0)

4. Estimate confidence (0.0 - 1.0)
   Based on:
   - number of articles
   - consistency

5. Provide short structured summary

Respond ONLY in JSON:
{{
  "event_type": "...",
  "location": "...",
  "severity": 0.0,
  "confidence": 0.0,
  "risk_score": 0.0,
  "summary": "..."
}}"""
        
        return prompt
    
    def _parse_risk_score(self, evaluation_text: str) -> Optional[float]:
        """Parse risk score from evaluation text (JSON or legacy format)"""
        try:
            # First try to parse as JSON
            try:
                # Extract JSON from response (might be wrapped in markdown code blocks)
                json_start = evaluation_text.find('{')
                json_end = evaluation_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = evaluation_text[json_start:json_end]
                    parsed = json.loads(json_str)
                    if 'risk_score' in parsed:
                        return float(parsed['risk_score'])
            except (json.JSONDecodeError, ValueError):
                pass  # Fall through to legacy parsing
            
            # Fallback to legacy "Risk Score: X.X" pattern
            for line in evaluation_text.split('\n'):
                if 'Risk Score:' in line.lower():
                    parts = line.split(':')
                    if len(parts) > 1:
                        score_str = parts[1].strip()
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
            logger.error(f"Failed to parse risk score: {e}", module='NEWS_EVALUATOR')
            return None
    
    def evaluate_with_fallback(self, news_data: Dict) -> tuple[bool, float, str]:
        """Evaluate news data trying all available models, then fall back to default"""
        success, risk_score, evaluation = self._evaluate(news_data, self.models)
        
        if success and risk_score is not None:
            return True, risk_score, evaluation
        
        # If all models fail, return default
        logger.error("All news evaluation models failed - using default risk score", module='NEWS_EVALUATOR')
        return False, 0.5, "Evaluation failed - using default risk score"
