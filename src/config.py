import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    API_KEY = os.environ.get("API_KEY", "la_clave_secreta_de_kiko")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    AZURE_STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
    AZURE_STORAGE_ACCOUNT_KEY = os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "")
    AZURE_CONTAINER_NAME = os.environ.get("AZURE_CONTAINER_NAME", "clientai")
    AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
    AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION", "eastus")
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
