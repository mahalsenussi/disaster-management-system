"""News module for data collection and evaluation"""
from .repository import NewsRepository
from .service import NewsService
from .validator import NewsValidator
from .collector import NewsCollector
from .evaluator import NewsEvaluator

__all__ = [
    'NewsRepository',
    'NewsService',
    'NewsValidator',
    'NewsCollector',
    'NewsEvaluator'
]
