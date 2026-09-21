"""
Web search and extraction tools for agents
"""

from typing import Any
from urllib.parse import quote_plus

import requests


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML scraping (no API key needed)"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)

        # Simple extraction of result snippets
        from html.parser import HTMLParser

        class ResultParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_result = False
                self.current = {}
                self.depth = 0

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and attrs_dict.get("class") == "result__url":
                    self.in_result = True
                    self.current["url"] = attrs_dict.get("href", "")
                elif tag == "a" and attrs_dict.get("class") == "result__snippet":
                    self.in_result = True
                    self.depth = 1

            def handle_data(self, data):
                if self.in_result and self.depth == 1:
                    self.current["snippet"] = data.strip()
                    self.results.append(self.current.copy())
                    self.current = {}
                    self.in_result = False
                    self.depth = 0

        parser = ResultParser()
        parser.feed(response.text)

        results = parser.results[:max_results]
        if not results:
            return "No results found"

        output = []
        for i, r in enumerate(results, 1):
            output.append(
                f"{i}. {r.get('snippet', 'No snippet')} (Source: {r.get('url', 'Unknown')})"
            )

        return "\n".join(output)
    except Exception as e:
        return f"Search error: {e!s}"


def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch and extract text content from a URL"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        # Simple HTML text extraction
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.ignore = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "noscript"):
                    self.ignore = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "noscript"):
                    self.ignore = False

            def handle_data(self, data):
                if not self.ignore and data.strip():
                    self.text.append(data.strip())

        extractor = TextExtractor()
        extractor.feed(response.text)

        full_text = " ".join(extractor.text)
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "... [truncated]"

        return full_text
    except Exception as e:
        return f"Error fetching URL: {e!s}"


def get_web_tools() -> list[dict[str, Any]]:
    """Get all web tools as a list of tool definitions"""
    return [
        {
            "name": "web_search",
            "description": "Search the web for information (uses DuckDuckGo, no API key needed)",
            "function": web_search,
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 5,
                },
            },
        },
        {
            "name": "fetch_url",
            "description": "Fetch and extract text content from a URL",
            "function": fetch_url,
            "parameters": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 5000,
                },
            },
        },
    ]
