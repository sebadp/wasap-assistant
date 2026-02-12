from fastapi import Request

from app.commands.registry import CommandRegistry
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.database.repository import Repository
from app.llm.client import OllamaClient
from app.memory.markdown import MemoryFile
from app.whatsapp.client import WhatsAppClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_whatsapp_client(request: Request) -> WhatsAppClient:
    return request.app.state.whatsapp_client


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_conversation_manager(request: Request) -> ConversationManager:
    return request.app.state.conversation_manager


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_command_registry(request: Request) -> CommandRegistry:
    return request.app.state.command_registry


def get_memory_file(request: Request) -> MemoryFile:
    return request.app.state.memory_file
