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

    # Skills
    skills_dir: str = "skills"

    # MCP
    mcp_config_path: str = "data/mcp_servers.json"

    # Tool router
    max_tools_per_call: int = 8

    # Memory (Phase 5)
    memory_dir: str = "data/memory"
    daily_log_days: int = 2
    memory_flush_enabled: bool = True

    # Embeddings & Semantic Search (Phase 6)
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    semantic_search_enabled: bool = True
    semantic_search_top_k: int = 10
    memory_file_watch_enabled: bool = True

    # User profiles & onboarding (Phase 8)
    onboarding_enabled: bool = True
    profile_discovery_interval: int = 10  # messages between progressive discovery runs

    # Guardrails (Fase 1)
    guardrails_enabled: bool = True
    guardrails_language_check: bool = True
    guardrails_pii_check: bool = True
    guardrails_llm_checks: bool = False  # Activar en Iteración 6

    # Tracing (Fase 2)
    tracing_enabled: bool = True
    tracing_sample_rate: float = 1.0  # 1.0 = trace everything
    trace_retention_days: int = 90

    # Evaluation (Fase 3+)
    eval_auto_curate: bool = True

    model_config = {"env_file": ".env"}
