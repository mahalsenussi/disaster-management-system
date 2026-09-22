"""
Vessel-capsize risk evaluator using Ollama LLM.

Draws on CMEMS-era forced variables (wave height/period, wind, currents, sea-level
anomaly) to produce an operational narrative for the hottest risk zone(s), explaining
why the zone is dangerous for small vessels and what to watch.
"""
import os
import re
import requests
from typing import Dict, Optional, Tuple, List
from evaluation_service.core.logger import get_logger
from evaluation_service.core.ollama import resolve_models

logger = get_logger()


class MarineEvaluator:
    """Evaluates marine/vessel risk using Ollama LLM."""

    def __init__(self, ollama_url: str = None):
        self.ollama_url = ollama_url or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
        self.cloud_model = os.environ.get('OLLAMA_MODEL', 'gemma4:31b-cloud')
        self.local_model = os.environ.get('OLLAMA_MODEL', 'gpt-oss:20b-cloud')
        self.models = resolve_models(self.ollama_url, preferred=self.cloud_model,
                                     fallback=self.local_model)
        # Slow cloud/thinking models caused multi-minute stalls; try fast local
        # models first and push any 'thinking' model to the very end.
        if self.models:
            self.models = [m for m in self.models if 'thinking' not in m.lower()] + \
                          [m for m in self.models if 'thinking' in m.lower()]
            logger.info(f"Resolved Ollama models: {self.models}", module='MARINE_EVALUATOR')

    def evaluate(self, risk_rows: List[Dict]) -> Tuple[bool, Optional[Dict]]:
        """Evaluate the highest-risk zone.

        Returns:
            (success, {zone, risk_score, danger_level, evaluation})
        """
        if not risk_rows:
            return False, None
        hottest = max(risk_rows, key=lambda r: r.get('risk_score') or 0)
        prompt = self._build_prompt(hottest)

        for model in (self.models or []):
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=30,
                )
                response.raise_for_status()
                text = (response.json().get('response') or '').strip()
                if not text:
                    continue
                logger.ai_call(model, len(prompt))
                return True, {
                    'zone': hottest.get('zone'),
                    'risk_score': hottest.get('risk_score'),
                    'danger_level': hottest.get('danger_level'),
                    'evaluation': text,
                }
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}", module='MARINE_EVALUATOR')

        # Deterministic fallback if Ollama is unreachable
        return True, {
            'zone': hottest.get('zone'),
            'risk_score': hottest.get('risk_score'),
            'danger_level': hottest.get('danger_level'),
            'evaluation': self._fallback_text(hottest),
        }

    def _build_prompt(self, row: Dict) -> str:
        return f"""You are a maritime search & rescue risk assessor operating in Libyan waters in the Central Mediterranean.

A zone off the coast near {row.get('zone') or 'unknown'} currently has these sea conditions:
- Significant wave height: {row.get('wave_height')} m
- Mean wave period: {row.get('wave_period')} s
- Wind speed: {row.get('wind_speed')} m/s
- Surface current speed: {row.get('current_speed')} m/s
- Sea level anomaly: {row.get('sea_level_anomaly')} m
- Composite small-vessel risk score: {row.get('risk_score')} / 1.0 ({row.get('danger_level')})

This is the departure/transit corridor for small boats and irregular migration vessels,
where capsizing and drowning incidents recur. Produce a concise operational brief:
1. WHY this zone is dangerous right now (physical mechanisms: wave breaking, short chop,
   current-wind shearing, tidal/storm-surge effect).
2. Which conditions pose the greatest immediate threat to a small inflatable-type vessel.
3. Recommended monitoring frequency and what escalation triggers to watch in the next 12 h.
Keep it under 180 words, plain language, no markdown tables."""
        # noqa: E501

    def _fallback_text(self, row: Dict) -> str:
        level = row.get('danger_level', 'LOW')
        zone = row.get('zone', 'unknown')
        return (f"Zone {zone} ({level} risk, score {row.get('risk_score')}): "
                f"wave height {row.get('wave_height')} m at {row.get('wave_period')} s period, "
                f"wind {row.get('wind_speed')} m/s, current {row.get('current_speed')} m/s. "
                f"For small-craft this combination favors short steep seas and risk of "
                f"swamping/capsizing. Recommend elevated monitoring in the next 12 h.")