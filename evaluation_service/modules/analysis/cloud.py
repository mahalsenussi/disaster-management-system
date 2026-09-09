"""
Direct Ollama.com cloud client for fast hosted generation.

Used instead of routing through the local Ollama daemon so we don't depend on
`ollama signin` state or local GPU/CPU resources. The API key is read from the
OLLAMA_API_KEY env var or from the ollama_cloud_key file next to this module.
"""
import json
import os

import requests

from evaluation_service.core.logger import get_logger

logger = get_logger()

CLOUD_BASE = os.environ.get('OLLAMA_CLOUD_URL', 'https://ollama.com')
DEFAULT_CLOUD_MODELS = [
    'gemma4:31b',
    'gpt-oss:20b',
    'nemotron-3-nano:30b',
]


def load_api_key():
    """Load the Ollama.com API key from env or a local config file."""
    key = os.environ.get('OLLAMA_API_KEY')
    if key:
        return key.strip()
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, '..', '..', 'ollama_cloud_key'),
                      os.path.join(here, 'ollama_cloud_key'),
                      '/home/mahmoud/disaster_management/evaluation_service/ollama_cloud_key'):
        try:
            with open(candidate) as fh:
                key = fh.read().strip()
            if key:
                return key
        except OSError:
            continue
    return None


class OllamaCloudClient:
    def __init__(self, models=None, timeout=120):
        self.api_key = load_api_key()
        self.models = models or DEFAULT_CLOUD_MODELS
        self.timeout = timeout
        self.max_tokens = 800
        self.base = os.environ.get('OLLAMA_CLOUD_URL', 'https://ollama.com')

    @property
    def available(self):
        return bool(self.api_key)

    def generate(self, prompt):
        """Try each cloud model in order; return (text, model) or (None, error)."""
        if not self.api_key:
            return None, 'No OLLAMA_API_KEY configured'
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        last_err = None
        for model in self.models:
            try:
                resp = requests.post(
                    f"{self.base}/api/generate",
                    headers=headers,
                    json={"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2, "num_predict": self.max_tokens}},
                    timeout=self.timeout,
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    return None, f'Cloud auth failed ({resp.status_code})'
                if resp.status_code == 402:
                    logger.warning(f'Cloud model {model} requires credits (402)', module='ANALYSIS')
                    continue
                data = resp.json()
                text = (data.get('response') or '').strip()
                if text:
                    return text, model
                last_err = f'{model}: empty response'
            except Exception as e:
                last_err = f'{model}: {e}'
                logger.warning(f'Cloud generate failed for {model}: {e}', module='ANALYSIS')
        return None, f'All cloud models failed: {last_err}'