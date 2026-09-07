"""
Ollama helper for model discovery and fallback
"""
import os
import requests
from typing import List, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()


def get_available_models(ollama_url: str = "http://localhost:11434") -> List[str]:
    """List models available on the Ollama server"""
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = [m.get('name', '') for m in response.json().get('models', [])]
            return [m for m in models if m]
    except Exception as e:
        logger.warning(f"Failed to list Ollama models: {e}", module='OLLAMA')
    return []


def resolve_models(ollama_url: str = "http://localhost:11434",
                   preferred: Optional[str] = None,
                   fallback: Optional[str] = None) -> List[str]:
    """Resolve the ordered list of models to try for generation.

    Priority:
    1. preferred model (explicitly requested, e.g. from env OLLAMA_MODEL)
    2. Any model actually available on the Ollama server
    3. fallback model name (last resort)
    """
    candidates = []
    if preferred:
        candidates.append(preferred)
    if fallback:
        candidates.append(fallback)

    available = get_available_models(ollama_url)

    ordered = []
    for candidate in candidates:
        if candidate not in ordered:
            ordered.append(candidate)

    for model in available:
        if model not in ordered:
            ordered.append(model)

    return ordered