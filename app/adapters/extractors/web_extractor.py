import time
from collections.abc import Iterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from app.config import settings
from app.domain.schemas import ColumnInfo, SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor


class WebExtractor(BaseExtractor):
    """
    Extrae HTML respetando robots.txt, User-Agent y rate limit.

    config:
      url, item_selector, fields: {nombre: "h2::text" | "a::attr(href)"}
      next_selector o load_more_selector (paginación / "cargar más")
      pagination: {type: page, param: page, max_pages: 20}
      rate_limit (segundos, default 1), max_pages, respect_robots (default true)
    """

    def connect(self) -> None:
        if "url" not in self.config or "item_selector" not in self.config:
            raise ValueError("Web requiere 'url' e 'item_selector'")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.USER_AGENT})
        self.robots: RobotFileParser | None = None
        if self.config.get("respect_robots", True):
            self._load_robots(self.config["url"])

    def close(self) -> None:
        session = getattr(self, "session", None)
        if session is not None:
            session.close()

    def _load_robots(self, url: str) -> None:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            self.robots = parser
        except Exception:
            self.robots = None

    def _allowed(self, url: str) -> bool:
        if not self.config.get("respect_robots", True):
            return True
        if self.robots is None:
            return True
        return self.robots.can_fetch(settings.USER_AGENT, url)

    def discover_schema(self) -> SourceSchema:
        fields = self.config.get("fields") or {}
        columns = [ColumnInfo(name=name, type="string", nullable=True) for name in fields]
        return SourceSchema(tables=[TableInfo(name=self.config.get("table") or "default", columns=columns)])

    @staticmethod
    def _extract_field(item, selector: str):
        if "::attr(" in selector:
            css, attr = selector.split("::attr(", 1)
            attr = attr.rstrip(")")
            element = item.select_one(css) if css else item
            return element.get(attr) if element is not None else None
        if selector.endswith("::text"):
            element = item.select_one(selector[: -len("::text")])
            return element.get_text(strip=True) if element is not None else None
        element = item.select_one(selector)
        return element.get_text(strip=True) if element is not None else None

    def _page_url(self, base: str, page: int) -> str:
        pagination = self.config.get("pagination") or {}
        param = pagination.get("param", "page")
        parts = urlsplit(base)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query[param] = str(page)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _fetch(self, url: str) -> BeautifulSoup | None:
        if not self._allowed(url):
            return None
        response = self.session.get(url, timeout=self.config.get("timeout", 15))
        self.last_http_status = response.status_code
        self.bytes_read += len(response.content or b"")
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        parser = self.config.get("parser", "html.parser")
        return BeautifulSoup(response.text, parser)

    def _emit(self, soup: BeautifulSoup) -> Iterator[dict]:
        fields = self.config.get("fields") or {}
        for item in soup.select(self.config["item_selector"]):
            yield {name: self._extract_field(item, selector) for name, selector in fields.items()}

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        del table, batch_size, checkpoint
        rate = float(self.config.get("rate_limit", 1.0) or 0)
        max_pages = int(self.config.get("max_pages") or (self.config.get("pagination") or {}).get("max_pages") or 100)
        next_selector = self.config.get("next_selector") or self.config.get("load_more_selector")
        pagination = self.config.get("pagination") or {}
        url = self.config["url"]
        page = 0

        while url and page < max_pages:
            soup = self._fetch(url)
            if soup is None:
                break
            yield from self._emit(soup)
            page += 1
            if next_selector:
                href = self._extract_field(soup, next_selector)
                url = urljoin(url, href) if href else None
            elif pagination.get("type") == "page":
                url = self._page_url(self.config["url"], page + int(pagination.get("start", 1)))
            else:
                url = None
            if url and rate > 0:
                time.sleep(rate)
