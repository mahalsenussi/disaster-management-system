"""Coastal module for marine data collection"""
from .repository import CoastalRepository
from .service import CoastalService
from .validator import CoastalValidator
from .collector import CoastalCollector

__all__ = [
    'CoastalRepository',
    'CoastalService',
    'CoastalValidator',
    'CoastalCollector'
]
