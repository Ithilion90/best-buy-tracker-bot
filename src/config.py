import os
import sys
from dataclasses import dataclass
from dotenv import load_dotenv, find_dotenv

# Load .env from project or workspace if present
load_dotenv(find_dotenv(), override=False)
# Also try loading .env from the executable directory when frozen (PyInstaller)
try:
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None
    if exe_dir:
        env_path = os.path.join(exe_dir, ".env")
        if os.path.isfile(env_path):
            load_dotenv(env_path, override=False)
except Exception:
    pass

@dataclass(frozen=True)
class Config:
    # Telegram
    bot_token: str = os.getenv("BOT_TOKEN", "")
    check_interval_minutes: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
    # Storage
    database_path: str = os.getenv("DATABASE_PATH", "tracker.db")
    database_url: str = os.getenv("DATABASE_URL", "")  # e.g. postgres://user:pass@host:5432/dbname
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    # HTTP
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
    user_agent: str = os.getenv("USER_AGENT", "Mozilla/5.0")
    # Affiliate
    affiliate_tag: str = os.getenv("AFFILIATE_TAG", "bestbuytracker-21")
    # Amazon Product Advertising API (PA API 5.0) - LEGAL alternative to scraping
    amazon_access_key: str = os.getenv("AMAZON_ACCESS_KEY", "")
    amazon_secret_key: str = os.getenv("AMAZON_SECRET_KEY", "")
    # Keepa (optional, for historical price data)
    keepa_api_key: str = os.getenv("KEEPA_API_KEY", "")
    keepa_domain: str = os.getenv("KEEPA_DOMAIN", "it")  # e.g., com, it, de

config = Config()

def validate_config() -> None:
    token = (config.bot_token or "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN not set. Create a .env file with BOT_TOKEN=<your real token> or set the env var."
        )
    # Basic sanity check: Telegram tokens are of the form <digits>:<alphanum>
    if ":" not in token:
        raise RuntimeError("BOT_TOKEN format looks invalid. Get a valid token from @BotFather.")
    
    # Validate Amazon PA API credentials
    if not config.amazon_access_key or not config.amazon_secret_key:
        raise RuntimeError(
            "Amazon Product Advertising API credentials not set.\n"
            "Add to .env:\n"
            "  AMAZON_ACCESS_KEY=<your access key>\n"
            "  AMAZON_SECRET_KEY=<your secret key>\n"
            "Get credentials from: https://webservices.amazon.com/paapi5/documentation/register-for-pa-api.html"
        )
    
    # Normalize database_path for frozen executables when relative
    if not os.path.isabs(config.database_path):
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        abs_db = os.path.join(base_dir, config.database_path)
        # mutate frozen dataclass via object.__setattr__ since frozen=True
        object.__setattr__(config, "database_path", abs_db)
