import yaml
from pathlib import Path
from typing import Set
import fnmatch
import os
import logging

logger = logging.getLogger(__name__)

class Config:
    def __init__(self):
        self.config_path = Path(__file__).parent / "config.yaml"
        self.load_config()

    def load_config(self):
        if not self.config_path.exists():
            self.config = {"ignored_domains": []}
            self.save_config()
        else:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)

    def save_config(self):
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def is_domain_ignored(self, domain: str) -> bool:
        """Check if a domain matches any of the ignored patterns"""
        patterns = self.config.get('ignored_domains', [])
        return any(fnmatch.fnmatch(domain.lower(), pattern.lower()) for pattern in patterns)

    def add_ignored_domain(self, pattern: str):
        """Add a new domain pattern to the ignored list"""
        if 'ignored_domains' not in self.config:
            self.config['ignored_domains'] = []
        if pattern not in self.config['ignored_domains']:
            self.config['ignored_domains'].append(pattern)
            self.save_config()

    def remove_ignored_domain(self, pattern: str):
        """Remove a domain pattern from the ignored list"""
        if 'ignored_domains' in self.config:
            self.config['ignored_domains'] = [
                p for p in self.config['ignored_domains'] if p != pattern
            ]
            self.save_config()

class ReaderConfig:
    def __init__(self):
        self.excluded_patterns: Set[str] = set()
        self._load_config()

    def _load_config(self):
        config_path = Path("config/reader_config.yaml")
        if not config_path.exists():
            print("Warning: reader_config.yaml not found, creating default config")
            self._create_default_config(config_path)

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                self.excluded_patterns = set(config.get('excluded_domains', []))
        except Exception as e:
            print(f"Error loading config: {e}")
            self.excluded_patterns = set()

    def _create_default_config(self, config_path: Path):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = {
            'excluded_domains': [
                'localhost',
                '127.0.0.1',
                '192.168.*.*',
                '10.*.*.*'
            ]
        }
        with open(config_path, 'w') as f:
            yaml.safe_dump(default_config, f, default_flow_style=False)

    def is_domain_excluded(self, domain: str) -> bool:
        """
        Check if a domain matches any exclusion pattern.
        Supports glob-style wildcards (* and ?)
        Examples:
            - '*.example.com' matches any subdomain of example.com
            - 'reddit-*.com' matches reddit-video.com, reddit-static.com, etc.
            - '192.168.*.*' matches any IP in the 192.168.0.0/16 subnet
        """
        domain = domain.lower()

        # Check each pattern
        for pattern in self.excluded_patterns:
            pattern = pattern.lower()

            # Handle IP address patterns specially
            if any(c.isdigit() for c in pattern):
                if self._match_ip_pattern(domain, pattern):
                    return True

            # Handle domain patterns
            if fnmatch.fnmatch(domain, pattern):
                return True
            # Also check if the pattern matches when prepended with a dot
            # This handles cases like 'example.com' matching 'subdomain.example.com'
            if fnmatch.fnmatch(domain, f"*.{pattern}"):
                return True

        return False

    def _match_ip_pattern(self, domain: str, pattern: str) -> bool:
        """
        Special handling for IP address patterns.
        Handles cases like '192.168.*.*' matching '192.168.1.1'
        """
        # Skip if domain isn't IP-like
        if not any(c.isdigit() for c in domain):
            return False

        # Split into octets
        domain_parts = domain.split('.')
        pattern_parts = pattern.split('.')

        # Must have same number of parts
        if len(domain_parts) != len(pattern_parts):
            return False

        # Check each octet
        for domain_part, pattern_part in zip(domain_parts, pattern_parts):
            if pattern_part == '*':
                continue
            if domain_part != pattern_part:
                return False

        return True

DEFAULT_CONFIG_PATH = 'config/reader_config.yaml'
USER_CONFIG_DIR = os.path.expanduser("~/.config/browser-recall")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, 'reader_config.yaml')

class Config:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path=None):
        if self._initialized:
            return
        self._initialized = True

        self.config_path = self._determine_config_path(config_path)
        self.config_data = self._load_config()
        logger.info(f"Config initialized using: {self.config_path}")
        # Pre-process excluded domains for faster lookup if needed,
        # but direct iteration with fnmatch is often fine for moderate lists.
        self.excluded_domains = self.config_data.get('excluded_domains', [])
        # Ensure it's a list
        if not isinstance(self.excluded_domains, list):
            logger.warning(f"Excluded domains in config is not a list: {self.excluded_domains}. Ignoring.")
            self.excluded_domains = []


    def _determine_config_path(self, provided_path):
        """Determine the correct config path to use."""
        if provided_path and os.path.exists(provided_path):
            return provided_path
        if os.path.exists(USER_CONFIG_PATH):
            return USER_CONFIG_PATH
        if os.path.exists(DEFAULT_CONFIG_PATH):
            return DEFAULT_CONFIG_PATH
        logger.warning("No configuration file found at default or user locations. Using empty config.")
        return None # Indicate no file was found

    def _load_config(self):
        """Loads the YAML configuration file."""
        if not self.config_path:
            return {} # Return empty dict if no config file path determined

        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {} # Return empty dict if file is empty
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {self.config_path}. Using default settings.")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file {self.config_path}: {e}")
            return {} # Return empty dict on parsing error
        except Exception as e:
            logger.error(f"Unexpected error loading configuration {self.config_path}: {e}")
            return {}

    def get_config(self):
        """Returns the loaded configuration data."""
        return self.config_data

    def reload_config(self):
        """Reloads the configuration from the file."""
        logger.info(f"Reloading configuration from: {self.config_path}")
        self.config_data = self._load_config()
        self.excluded_domains = self.config_data.get('excluded_domains', [])
        if not isinstance(self.excluded_domains, list):
            logger.warning(f"Excluded domains in reloaded config is not a list: {self.excluded_domains}. Ignoring.")
            self.excluded_domains = []
        logger.info("Configuration reloaded.")


    def is_domain_ignored(self, domain: str) -> bool:
        """
        Checks if a given domain matches any pattern in the excluded_domains list.
        Supports exact matches and wildcard (*) matching using fnmatch.
        """
        if not domain: # Ignore empty domains
            return True
        if not self.excluded_domains: # If list is empty, nothing is ignored
             return False

        # Normalize domain to lowercase for case-insensitive comparison
        domain_lower = domain.lower()

        for pattern in self.excluded_domains:
            if not isinstance(pattern, str): # Skip non-string patterns
                continue

            # Normalize pattern to lowercase
            pattern_lower = pattern.lower()

            # Use fnmatch.fnmatch for wildcard support (*)
            if fnmatch.fnmatch(domain_lower, pattern_lower):
                # logger.debug(f"Domain '{domain}' ignored due to pattern '{pattern}'")
                return True
        return False

    # --- Add methods to get specific config values safely ---
    @property
    def history_update_interval_seconds(self) -> int:
        """Gets the history update interval, defaulting to 300."""
        return self.config_data.get('history_update_interval_seconds', 300)

    @property
    def markdown_update_interval_seconds(self) -> int:
        """Gets the markdown update interval, defaulting to 300."""
        return self.config_data.get('markdown_update_interval_seconds', 300)

    # Add other specific getters as needed
    # Example:
    # @property
    # def some_other_setting(self) -> str:
    #     return self.config_data.get('some_other_setting', 'default_value')