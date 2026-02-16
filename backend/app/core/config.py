
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
dotenv_path = Path(__file__).resolve().parent.parent.parent.parent / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)

class Settings:
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    HOSPITALS_JSON_PATH: str = os.getenv("HOSPITALS_JSON_PATH", "")
    RATES_JSON_PATH: str = os.getenv("RATES_JSON_PATH", "")

    # Paths validation
    @property
    def is_ocr_configured(self) -> bool:
        return bool(self.GOOGLE_API_KEY and self.GOOGLE_APPLICATION_CREDENTIALS)

    @property
    def is_data_configured(self) -> bool:
        return bool(self.HOSPITALS_JSON_PATH and self.RATES_JSON_PATH and 
                   Path(self.HOSPITALS_JSON_PATH).exists() and 
                   Path(self.RATES_JSON_PATH).exists())

settings = Settings()
