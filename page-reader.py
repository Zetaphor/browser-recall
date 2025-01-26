import httpx
import re
from markdownify import markdownify as md
from bs4 import BeautifulSoup

# Patterns for cleaning
SCRIPT_PATTERN = r"<[ ]*script.*?\/[ ]*script[ ]*>"
STYLE_PATTERN = r"<[ ]*style.*?\/[ ]*style[ ]*>"
META_PATTERN = r"<[ ]*meta.*?>"
COMMENT_PATTERN = r"<[ ]*!--.*?--[ ]*>"
LINK_PATTERN = r"<[ ]*link.*?>"
BASE64_IMG_PATTERN = r'<img[^>]+src="data:image/[^;]+;base64,[^"]+"[^>]*>'
SVG_PATTERN = r"(<svg[^>]*>)(.*?)(<\/svg>)"

def clean_html(html: str) -> str:
    """Clean HTML by removing unwanted elements and patterns."""
    # First use regex to remove problematic patterns
    html = re.sub(SCRIPT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(STYLE_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(META_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(COMMENT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(LINK_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(SVG_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    html = re.sub(BASE64_IMG_PATTERN, "", html)

    # Use BeautifulSoup to remove additional elements we want to strip
    soup = BeautifulSoup(html, 'html.parser')

    # Remove unwanted elements
    elements_to_remove = [
        'canvas', 'img', 'picture', 'audio', 'video',
        'iframe', 'embed', 'object', 'param', 'track',
        'map', 'area', 'source'
    ]

    for element in elements_to_remove:
        for tag in soup.find_all(element):
            tag.decompose()

    return str(soup)

def get_page_html(url: str) -> str:
    """Fetch HTML content from a given URL using httpx."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        with httpx.Client(follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as e:
        print(f"Error fetching page: {e}")
        return ""

def clean_whitespace(text: str) -> str:
    """Clean excessive whitespace from text, collapsing more than 2 newlines."""
    # Replace 3 or more newlines with 2 newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', text)
    # Remove trailing whitespace from each line
    cleaned = '\n'.join(line.rstrip() for line in cleaned.splitlines())
    return cleaned.strip()

def html_to_markdown(url: str) -> str:
    """Convert webpage HTML to markdown."""
    html = get_page_html(url)
    if not html:
        return ""

    # Clean the HTML first
    cleaned_html = clean_html(html)

    # Convert to markdown using markdownify
    # Configure markdownify options for clean output
    markdown = md(cleaned_html,
                 heading_style="ATX",  # Use # style headers
                 bullets="-",          # Use - for bullets
                 autolinks=True,       # Convert URLs to links
                 strip=['form'],       # Additional elements to strip
                 escape_asterisks=True,
                 escape_underscores=True)

    # Clean up excessive whitespace
    return clean_whitespace(markdown)

if __name__ == "__main__":
    # Example usage
    url = "https://reddit.com"
    markdown_content = html_to_markdown(url)
    print(markdown_content)
