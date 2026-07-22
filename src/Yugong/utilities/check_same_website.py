from src.Yugong.core.settings import settings


def check_same_website(url: str) -> bool:
    from urllib.parse import urlparse

    def normalize_domain(domain: str) -> str:
        """Remove www prefix and lowercase the domain."""
        if not domain:
            return ""
        domain = domain.lower()
        # Remove port number if present (e.g., example.com:8080 -> example.com)
        if ':' in domain:
            domain = domain.split(':')[0]
        if domain.startswith("www."):
            return domain[4:]
        return domain

    def extract_domain(address: str) -> str:
        """Extract the netloc (domain) from a URL or address string."""
        if not address:
            return ""
        
        parsed = urlparse(address)
        netloc = parsed.netloc
        
        # If netloc is empty, it might be because the scheme was missing 
        # and urlparse treated the whole thing as a path, or it's just a raw domain.
        if not netloc:
            # Try adding a scheme to see if it parses correctly
            if not address.startswith(("http://", "https://")):
                temp_parsed = urlparse(f"https://{address}")
                netloc = temp_parsed.netloc
        
        return netloc

    try:
        # Extract and normalize domain from the input URL
        url_domain_raw = extract_domain(url)
        normalized_url_domain = normalize_domain(url_domain_raw)
        
        if not normalized_url_domain:
            return False

        # Extract and normalize domain from the API endpoint setting
        api_endpoint = settings.api_endpoint
        api_domain_raw = extract_domain(api_endpoint)
        normalized_api_domain = normalize_domain(api_domain_raw)
        
        if not normalized_api_domain:
            return False

        return normalized_url_domain == normalized_api_domain
    except Exception:
        return False
