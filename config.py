from os import environ
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration."""

    SENSEBOX_IDS = environ.get("SENSEBOX_IDS", "").split(",")
    OPENSENSEMAP_BASE_URL = environ.get(
        "OPENSENSEMAP_BASE_URL", "https://api.opensensemap.org"
    )
    APP_VERSION = environ.get("APP_VERSION", "v0.0.1")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
