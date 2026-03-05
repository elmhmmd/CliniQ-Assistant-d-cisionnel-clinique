from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://cliniq:cliniq@localhost:5432/cliniq"

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # RAG
    ollama_model: str = "mistral"
    retriever_k: int = 5

    # MLflow
    mlflow_tracking_uri: str = "http://mlflow:5000"


settings = Settings()
