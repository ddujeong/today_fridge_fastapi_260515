from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DB / Redis
    database_url: str
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Spring Boot 연동 (application.yml: app.fastapi.service-key / caller-service)
    internal_service_token: str = "change-me"
    internal_caller_service: str = "spring-backend"

    # 로컬 AI 모델
    yolo_model_path: str = "models/yolo/fridge_detect/weights/best.pt"
    chroma_db_path: str = "models/chroma_db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    embedding_model: str = "jhgan/ko-sroberta-multitask"

    # 네이버 CLOVA OCR (PaddleOCR 로컬 우선, 전환용)
    clova_ocr_api_key_id: str = ""
    clova_ocr_api_key: str = ""

    # 네이버 검색 API (쇼핑 최저가)
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # 쿠팡 파트너스 (딥링크)
    coupang_partners_id: str = ""

    # KAMIS 농산물 시세
    kamis_api_key: str = ""

    # Google Cloud Vision (선택적)
    google_cloud_project_id: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
