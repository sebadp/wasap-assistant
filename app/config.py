from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WhatsApp Cloud API
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str
    whatsapp_app_secret: str
    allowed_phone_numbers: list[str]

    @field_validator("allowed_phone_numbers", mode="before")
    @classmethod
    def parse_phone_numbers(cls, v: object) -> object:
        if isinstance(v, str):
            return [n.strip() for n in v.split(",") if n.strip()]
        if isinstance(v, (int, float)):
            return [str(int(v))]
        return v

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"
    system_prompt: str = (
        "You are a helpful personal assistant on WhatsApp. "
        "Be concise and friendly. Answer in the same language the user writes in."
    )
    conversation_max_messages: int = 20

    # ngrok (only used in docker-compose, not by the app itself)
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""

    # Logging
    log_level: str = "INFO"

    model_config = {"env_file": ".env"}
