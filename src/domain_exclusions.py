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
            return True # Exclude invalid URLs

        input_url_stripped = url_string.strip()

        try:
            parsed_url = urlparse(input_url_stripped)
            domain = parsed_url.netloc

            # Basic check: if domain itself is empty (can happen with file:// URLs etc.)
            if not domain:
                return True # Exclude URLs without a domain

            # Combine domain and path for path-specific exclusions
            path = parsed_url.path if parsed_url.path else ''
            # Ensure path starts with / if it exists and isn't empty, handle root case
            if not path.startswith('/') and path:
                 path = '/' + path
            elif not path:
                 path = '/' # Represent root path explicitly for matching
            domain_and_path = domain + path


            for pattern in self.excluded_domains:
                # 1. Check for path-specific patterns first (more specific)
                #    Use startswith for patterns like "github.com/settings"
                #    Ensure pattern doesn't end with '/' unless path is just '/'
                if '/' in pattern:
                     # Normalize pattern ending for comparison
                     normalized_pattern = pattern.rstrip('/')
                     normalized_domain_path = domain_and_path.rstrip('/')
                     # Handle root path case explicitly
                     if normalized_pattern == domain and path == '/':
                         # print(f"DEBUG: URL '{url_string}' excluded by root path pattern '{pattern}'")
                         return True
                     if normalized_domain_path.startswith(normalized_pattern) and normalized_pattern != domain:
                         # print(f"DEBUG: URL '{url_string}' excluded by path pattern '{pattern}' matching '{normalized_domain_path}'")
                         return True
                     continue # Don't check domain ending if it was a path pattern

                # 2. Check if the domain ends with the pattern (handles subdomains)
                #    Also check for exact match.
                #    Example: domain "ap.www.namecheap.com" ends with pattern "namecheap.com"
                #    Example: domain "localhost" matches pattern "localhost"
                #    Add '.' prefix for endswith check to avoid partial matches like 'example.com' matching 'ample.com'
                pattern_for_endswith = '.' + pattern if not pattern.startswith('.') else pattern
                domain_for_endswith = '.' + domain

                if domain == pattern or domain_for_endswith.endswith(pattern_for_endswith):
                    # print(f"DEBUG: URL '{url_string}' excluded by domain pattern '{pattern}' matching domain '{domain}'")
                    return True

                # 3. Check for patterns intended to match anywhere (like "login.", ".auth.")
                #    This is less precise but matches the original intent of some patterns.
                #    Check within the domain part only.
                if pattern.startswith('.') or pattern.endswith('.'):
                    if pattern in domain:
                         # print(f"DEBUG: URL '{url_string}' excluded by substring pattern '{pattern}' in domain '{domain}'")
                         return True


        except ValueError:
             # Handle potential errors from urlparse on malformed URLs
             print(f"Warning: Could not parse URL '{url_string}' for exclusion check.")
             return True # Exclude unparseable URLs
        except Exception as e:
            # Log other errors during URL parsing or checking
            print(f"Warning: Error processing URL '{url_string}' for exclusion: {e}")
            return True # Exclude URLs that cause errors during processing

        # If no patterns matched
        return False