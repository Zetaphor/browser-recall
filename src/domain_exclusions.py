import yaml
from fnmatch import fnmatch

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
                self.excluded_domains = config
            else:
                self.excluded_domains = config.get('excluded_domains', [])
        except FileNotFoundError:
            print(f"Warning: Configuration file {config_path} not found. No domains will be excluded.")
        except yaml.YAMLError as e:
            print(f"Error parsing YAML configuration: {e}")
            self.excluded_domains = []

    def is_excluded(self, domain):
        """
        Check if a domain matches any of the excluded domain patterns.
        """
        # Strip protocol (http:// or https://) if present
        domain = domain.lower().strip('/')
        if '://' in domain:
            domain = domain.split('://', 1)[1]

        # Strip query parameters if present
        if '?' in domain:
            domain = domain.split('?', 1)[0]

        # Split domain and path
        if '/' in domain:
            domain = domain.split('/', 1)[0]

        for pattern in self.excluded_domains:
            pattern = pattern.lower().strip('/')
            if '/' in pattern:
                pattern = pattern.split('/', 1)[0]

            # Remove trailing wildcard if present
            if pattern.endswith('*'):
                pattern = pattern.rstrip('*').rstrip('.')

            # Use fnmatch for proper wildcard pattern matching
            if fnmatch(domain, pattern):
                return True
        return False