import yaml
from pathlib import Path
from typing import Set
import fnmatch

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