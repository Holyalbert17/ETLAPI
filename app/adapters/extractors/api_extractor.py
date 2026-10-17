import time
from collections.abc import Iterator

import requests

from app.config import settings
from app.domain.schemas import SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.infer import dig, infer_columns
from app.services.normalizer import to_jsonable


class APIExtractor(BaseExtractor):
    """
    config:
      url, method, headers, params, data_path
      pagination: {type: page, param: page, size_param: per_page, size: 100, max_pages: 50}
      rate_limit
    """

    def connect(self) -> None:
        if "url" not in self.config:
            raise ValueError("API requiere 'url'")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.USER_AGENT})
        extra = self.config.get("headers") or {}
        if not isinstance(extra, dict):
            raise ValueError("headers debe ser un objeto")
        self.session.headers.update({str(key): str(value) for key, value in extra.items()})

    def close(self) -> None:
        session = getattr(self, "session", None)
        if session is not None:
            session.close()

    def _fetch_page(self, page: int) -> list[dict]:
        params = dict(self.config.get("params") or {})
        pagination = self.config.get("pagination") or {}
        if pagination.get("type") == "page":
            params[pagination.get("param", "page")] = page
            if pagination.get("size_param"):
                params[pagination["size_param"]] = pagination.get("size", 100)
        response = self.session.request(
            self.config.get("method", "GET"),
            self.config["url"],
            params=params,
            timeout=self.config.get("timeout", 30),
        )
        self.last_http_status = response.status_code
        self.bytes_read += len(response.content or b"")
        response.raise_for_status()
        payload = dig(response.json(), self.config.get("data_path"))
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []
        return [to_jsonable(item) for item in payload if isinstance(item, dict)]

    def discover_schema(self) -> SourceSchema:
        sample = self._fetch_page(int((self.config.get("pagination") or {}).get("start", 1)))
        return SourceSchema(
            tables=[
                TableInfo(
                    name=self.config.get("table") or "default",
                    columns=infer_columns(sample),
                )
            ]
        )

    def extract(
        self,
        table: str,
        batch_size: int = 500,
        checkpoint: dict | None = None,
    ) -> Iterator[dict]:
        del table, batch_size, checkpoint
        pagination = self.config.get("pagination") or {}
        max_pages = int(pagination.get("max_pages") or 1)
        start = int(pagination.get("start", 1))
        size = int(pagination.get("size") or 100)
        rate = float(self.config.get("rate_limit") or 0)
        for page in range(start, start + max_pages):
            items = self._fetch_page(page)
            if not items:
                break
            yield from items
            if pagination.get("type") == "page" and len(items) < size:
                break
            if page < start + max_pages - 1 and rate > 0:
                time.sleep(rate)
