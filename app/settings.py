"""
Application settings loaded from environment variables.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BrowserlessSettings:
    """Browserless.io configuration for headless browser scraping."""
    api_key: Optional[str] = None
    api_url: str = "wss://chrome.browserless.io"
    enabled: bool = False

    @property
    def ws_endpoint(self) -> Optional[str]:
        """Get the WebSocket endpoint for Playwright."""
        if not self.enabled or not self.api_key:
            return None
        return f"{self.api_url}?token={self.api_key}"

    @classmethod
    def from_env(cls) -> "BrowserlessSettings":
        """Load settings from environment variables."""
        return cls(
            api_key=os.getenv("BROWSERLESS_API_KEY"),
            api_url=os.getenv("BROWSERLESS_API_URL", "wss://chrome.browserless.io"),
            enabled=os.getenv("USE_BROWSERLESS", "false").lower() == "true",
        )


@dataclass
class BrightDataSettings:
    """Bright Data proxy configuration."""
    # Browser API (WebSocket connection to Bright Data's browser)
    browser_ws: Optional[str] = None
    browser_enabled: bool = False

    # Residential proxy (for sites with strong bot protection like Ohio PUCO)
    residential_username: Optional[str] = None  # e.g., brd-customer-XXX-zone-residential_proxy1
    residential_password: Optional[str] = None
    residential_enabled: bool = False

    # Common settings
    host: str = "brd.superproxy.io"
    residential_port: int = 33335  # Residential proxy port

    @property
    def residential_proxy_config(self) -> Optional[dict]:
        """Get residential proxy config for Playwright context."""
        if not self.residential_enabled or not self.residential_username or not self.residential_password:
            return None
        return {
            "server": f"http://{self.host}:{self.residential_port}",
            "username": f"{self.residential_username}-country-us",
            "password": self.residential_password
        }

    @property
    def enabled(self) -> bool:
        """Check if any Bright Data mode is enabled."""
        return self.browser_enabled or self.residential_enabled

    @classmethod
    def from_env(cls) -> "BrightDataSettings":
        """Load settings from environment variables."""
        return cls(
            # Browser API (for non-government sites)
            browser_ws=os.getenv("BRIGHTDATA_BROWSER_WS"),
            browser_enabled=os.getenv("USE_BRIGHTDATA_BROWSER", "false").lower() == "true",
            # Residential proxy (for government sites with bot protection)
            residential_username=os.getenv("BRIGHTDATA_RESIDENTIAL_USERNAME"),
            residential_password=os.getenv("BRIGHTDATA_RESIDENTIAL_PASSWORD"),
            residential_enabled=os.getenv("USE_BRIGHTDATA_RESIDENTIAL", "false").lower() == "true",
            # Common
            host=os.getenv("BRIGHTDATA_HOST", "brd.superproxy.io"),
            residential_port=int(os.getenv("BRIGHTDATA_RESIDENTIAL_PORT", "33335")),
        )


@dataclass
class ScraperSettings:
    """Scraper-related settings."""
    # Timeouts
    page_timeout_ms: int = 30000
    network_idle_timeout_ms: int = 15000

    # Rate limiting (ms between requests)
    default_rate_limit_ms: int = 1000

    # Retry settings
    max_retries: int = 3
    retry_delay_ms: int = 2000

    # States that require special handling
    playwright_states: tuple = ("FL", "OH")  # Need JavaScript rendering
    proxy_states: tuple = ("OH",)  # Need proxy for bot protection

    @classmethod
    def from_env(cls) -> "ScraperSettings":
        return cls(
            page_timeout_ms=int(os.getenv("SCRAPER_PAGE_TIMEOUT_MS", "30000")),
            default_rate_limit_ms=int(os.getenv("SCRAPER_RATE_LIMIT_MS", "1000")),
            max_retries=int(os.getenv("SCRAPER_MAX_RETRIES", "3")),
        )


class Settings:
    """Main settings container."""
    _instance = None

    def __init__(self):
        self.browserless = BrowserlessSettings.from_env()
        self.brightdata = BrightDataSettings.from_env()
        self.scraper = ScraperSettings.from_env()

    @classmethod
    def get(cls) -> "Settings":
        """Get singleton settings instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls):
        """Reload settings from environment."""
        cls._instance = None
        return cls.get()


# Convenience function
def get_settings() -> Settings:
    return Settings.get()
