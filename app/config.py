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
    ollama_model: str = "qwen3:8b"
    system_prompt: str = (
        "You are a helpful personal assistant on WhatsApp. "
        "Be friendly. Answer in the same language the user writes in. "
        "Adapt your response length to the user's request — be brief for simple questions, "
        "detailed when asked for long or thorough answers."
    )
    conversation_max_messages: int = 20

    # Database
    database_path: str = "data/wasap.db"
    summary_threshold: int = 40

    # ngrok (only used in docker-compose, not by the app itself)
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Rate limiting
    rate_limit_max: int = 10
    rate_limit_window: int = 60

    # Audio (Whisper)
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Vision
    vision_model: str = "llava:7b"

    model_config = {"env_file": ".env"}
