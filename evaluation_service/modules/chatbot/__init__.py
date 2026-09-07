"""Chatbot module for general and medical chatbots"""
from .general_chat import GeneralChatbot
from .medical_chat import MedicalChatbot

__all__ = [
    'GeneralChatbot',
    'MedicalChatbot'
]
