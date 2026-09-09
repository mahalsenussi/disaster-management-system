"""
Summarizer: turns aggregated POI/branch context into structured AI summaries
using the local Ollama instance (lrc-assistant preferred).
"""
import json
import re
from datetime import datetime

import requests

from evaluation_service.core.logger import get_logger
from evaluation_service.core.ollama import get_available_models
from evaluation_service.modules.analysis.cloud import OllamaCloudClient

logger = get_logger()

PROMPT_TEMPLATE = """You are an emergency and disaster management analyst for the Libyan Red Crescent.

Based ONLY on the data below, produce a concise structured analysis. Respond with STRICT JSON
(no markdown, no code fences) of this exact shape:
{{
  "summaries": [
    {{
      "kind": "{kind}",
      "category": "string or null",
      "branch_id": <int or null>,
      "title": "short title",
      "counts": {{"total": <int>, ...other relevant numbers}},
      "one_liner": "one-sentence bottom line",
      "key_issues": ["issue 1", ...],
      "risk_level": "low|medium|high",
      "suggested_actions": ["action 1", ...],
      "summary": "2-4 sentence summary"
    }}
  ]
}}

The context is provided as a JSON list. For POI category context: highlight capacity/vacancy stress,
verification coverage and notable facilities. For branch context: highlight reporting cadence, open
incidents, follow-up workload and branch risk. Use language that matches the data (Arabic data -> Arabic text).

Context:
{contexts_json}
"""


class AnalysisSummarizer:
    def __init__(self, ollama_url="http://localhost:11434"):
        self.ollama_url = ollama_url
        # Fast path: hosted cloud models (free tier) via ollama.com API key
        self.cloud = OllamaCloudClient()
        # Local/configured fallbacks (slow CPU or paid cloud via local daemon)
        self.model_priority = [
            "minimax-m3:cloud",
            "minimax-m2.1:cloud",
            "command-r7b-arabic:7b",
            "lrc-assistant:latest",
        ]
        self.timeout = 120
        self.max_tokens = 800

    def _generate(self, prompt):
        """Fast cloud path first, then local model priority list."""
        # 1) Hosted cloud (free tier) - fast, no local GPU needed
        if self.cloud.available:
            text, model = self.cloud.generate(prompt)
            if text:
                return text, model
        # 2) Local daemon path
        try:
            available = [m.split(':')[0] for m in get_available_models(self.ollama_url)]
        except Exception:
            available = []
        candidates = []
        for m in self.model_priority:
            if m not in candidates:
                candidates.append(m)
        last_err = None
        for model in candidates:
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2, "num_predict": self.max_tokens},
                          "keep_alive": "5m"},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                text = resp.json().get('response', '').strip()
                if text:
                    return text, model
            except Exception as e:
                last_err = e
                logger.warning(f"Ollama generate failed for {model}: {e}", module='ANALYSIS')
        return None, f"All models failed: {last_err}"

    @staticmethod
    def _extract_json(text):
        """Robustly pull a JSON object out of an LLM response (balanced braces)."""
        if not text:
            return None
        candidate = text.strip()
        start = candidate.find('{')
        if start == -1:
            return None
        # Direct parse first
        try:
            return json.loads(candidate[start:])
        except json.JSONDecodeError:
            pass
        # Balanced-brace scan for the outermost object (handles trailing prose/fences)
        depth = 0
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def summarize(self, contexts, kind='poi_category'):
        """Return {'summaries': [...], 'model': ..., 'generated_at': ...}."""
        if not contexts:
            return {'summaries': [], 'model': None,
                    'generated_at': datetime.now().isoformat(), 'error': 'no context'}
        prompt = PROMPT_TEMPLATE.format(
            kind=kind,
            contexts_json=json.dumps(contexts, ensure_ascii=False)[:12000],
        )
        text, model = self._generate(prompt)
        if not text:
            return {'summaries': [], 'model': None,
                    'generated_at': datetime.now().isoformat(), 'error': model}
        parsed = self._extract_json(text)
        if not parsed or not isinstance(parsed.get('summaries'), list):
            # Graceful fallback: wrap the raw text into a single summary
            logger.warning('Summarizer returned non-JSON, wrapping raw text', module='ANALYSIS')
            parsed = {'summaries': [{
                'kind': kind,
                'category': None,
                'branch_id': None,
                'title': 'AI Summary',
                'counts': {'total': len(contexts)},
                'one_liner': '',
                'key_issues': [],
                'risk_level': 'medium',
                'suggested_actions': [],
                'summary': text[:2000],
            }]}
        return {'summaries': parsed['summaries'], 'model': model,
                'generated_at': datetime.now().isoformat()}