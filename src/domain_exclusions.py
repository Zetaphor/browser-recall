import yaml
from fnmatch import fnmatch
from urllib.parse import urlparse

class DomainExclusions:
    def __init__(self, config_path="config/history_config.yaml"):
        self.excluded_domains = []
        self.load_config(config_path)

    def load_config(self, config_path):
        """Load excluded domains from the YAML configuration file."""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Handle both direct list and dict with 'excluded_domains' key
            if isinstance(config, list):
                loaded_patterns = config
            elif isinstance(config, dict):
                loaded_patterns = config.get('excluded_domains', [])
            else:
                loaded_patterns = [] # Handle other invalid config types

            # Basic validation/cleaning of patterns
            self.excluded_domains = [
                str(p).strip() for p in loaded_patterns if p and isinstance(p, str)
            ]
            # Optional: Warn if some patterns were ignored
            # if len(self.excluded_domains) != len(loaded_patterns):
            #      print(f"Warning: Some invalid patterns were ignored in {config_path}")

        except FileNotFoundError:
            print(f"Warning: Configuration file {config_path} not found. No domains will be excluded.")
            self.excluded_domains = [] # Ensure it's empty on error
        except yaml.YAMLError as e:
            print(f"Error parsing YAML configuration: {e}")
            self.excluded_domains = []
        except Exception as e: # Catch other potential errors
            print(f"An unexpected error occurred during config loading: {e}")
            self.excluded_domains = []

    def is_excluded(self, url_string):
        if not url_string or not isinstance(url_string, str):
            return True

        input_url = url_string.strip()

        # If the url starts with www, remove it
        if input_url.startswith('www.'):
            input_url = input_url[4:]

        for pattern in self.excluded_domains:
            if pattern in input_url:
                return True

        # If no patterns matched
        return False