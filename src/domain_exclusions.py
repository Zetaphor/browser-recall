import yaml
from fnmatch import fnmatch

class DomainExclusions:
    def __init__(self, config_path="history_config.yaml"):
        self.excluded_domains = []
        self.load_config(config_path)

    def load_config(self, config_path):
        """Load excluded domains from the YAML configuration file."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Get the excluded_domains list from config, defaulting to empty list if not found
            self.excluded_domains = config.get('excluded_domains', [])
        except FileNotFoundError:
            print(f"Warning: Configuration file {config_path} not found. No domains will be excluded.")
        except yaml.YAMLError as e:
            print(f"Error parsing YAML configuration: {e}")
            self.excluded_domains = []

    def is_excluded(self, domain):
        """
        Check if a domain matches any of the excluded domain patterns.
        Supports wildcards (*, ?) in the excluded domain patterns.

        Args:
            domain (str): The domain to check

        Returns:
            bool: True if the domain should be excluded, False otherwise
        """
        return any(fnmatch(domain.lower(), pattern.lower()) for pattern in self.excluded_domains)