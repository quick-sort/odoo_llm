import io
import logging
from typing import Any

import requests
from markitdown import MarkItDown

from odoo import api, models

_logger = logging.getLogger(__name__)

_markitdown = MarkItDown()


class LLMToolWebSearch(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [
            ("web_search", "Web Search"),
            ("web_fetch", "Web Page Fetch"),
        ]

    def web_search_execute(
        self,
        query: str,
        num_results: int = 5,
    ) -> dict[str, Any]:
        """
        Search the web using Brave Search and return results.

        Use this tool when you need to find current information from the internet,
        look up facts, or find relevant web pages on a topic.

        Parameters:
            query: The search query string.
            num_results: Number of results to return (max 20).
        """
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("llm_tool_websearch.brave_api_key")
        )
        if not api_key:
            return {
                "error": "Brave Search API key not configured. "
                "Set system parameter: llm_tool_websearch.brave_api_key"
            }

        num_results = min(num_results, 20)
        try:
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": num_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            _logger.exception("Brave web search failed")
            return {"error": str(e)}

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description"),
            })

        return {"query": query, "results": results}

    def web_fetch_execute(
        self,
        urls: list[str],
    ) -> dict[str, Any]:
        """
        Fetch one or more web pages and extract their main readable content.
        Pages are fetched in parallel for efficiency.

        Use this tool after web_search to read the full content of relevant pages.

        Parameters:
            urls: List of URLs to fetch.
        """
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("llm_tool_websearch.brightdata_api_key")
        )
        zone = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("llm_tool_websearch.brightdata_zone", "web_unlocker1")
        )
        if not api_key:
            return {
                "error": "BrightData API key not configured. "
                "Set system parameter: llm_tool_websearch.brightdata_api_key"
            }

        from concurrent.futures import ThreadPoolExecutor

        def fetch_single(url):
            return self._fetch_url(url, api_key, zone)

        with ThreadPoolExecutor(max_workers=min(len(urls), 8)) as pool:
            results = list(pool.map(fetch_single, urls))

        return {"results": results}

    @api.model
    def _fetch_url(self, url, api_key, zone):
        """Fetch a single URL via BrightData and extract readable content."""
        html = None
        try:
            resp = requests.post(
                "https://api.brightdata.com/request",
                json={
                    "zone": zone,
                    "url": url,
                    "format": "raw",
                    "method": "GET",
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            resp.raise_for_status()
            brd_err = resp.headers.get('x-brd-err-code')
            if brd_err:
                return {"url": url, "error": resp.headers.get('x-brd-err-msg', brd_err)}
            html = resp.content
        except requests.RequestException as e:
            _logger.exception("BrightData fetch failed for %s", url)
            return {"url": url, "error": str(e)}

        if not html:
            return {"url": url, "content": ""}

        try:
            result = _markitdown.convert_stream(io.BytesIO(html), file_extension=".html")
            content = result.text_content.strip() if result and result.text_content else ""
        except Exception:
            _logger.warning("Failed to parse HTML from %s", url, exc_info=True)
            content = ""

        if not content:
            return {"url": url, "content": ""}

        # Strip null bytes - PostgreSQL jsonb cannot store \u0000
        content = content.replace('\x00', '')

        return {"url": url, "content": content}
