from fastapi import Request

from app.config import Settings
from app.conversation.manager import ConversationManager
from app.llm.client import OllamaClient
from app.whatsapp.client import WhatsAppClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_whatsapp_client(request: Request) -> WhatsAppClient:
    return request.app.state.whatsapp_client


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_conversation_manager(request: Request) -> ConversationManager:
    return request.app.state.conversation_manager
