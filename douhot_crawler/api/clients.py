from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .config import ApiSettings
from .errors import ExternalServiceError


class _HotspotRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None


class _HotspotData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    records: list[_HotspotRecord]


class _HotspotResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: int
    message: str = ""
    data: _HotspotData | None = None


class _CookieResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: int
    message: str = ""
    cookie: str | None = None


class ExternalApiClient:
    """Typed clients for keyword, Cookie, and ranking external APIs."""

    def __init__(
        self,
        settings: ApiSettings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.read_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            )
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _post_json(
        self,
        service: str,
        url: str,
        payload: Any,
        *,
        sensitive_response: bool = False,
    ) -> Any:
        delays = (0.0, 2.0, 5.0, 10.0)
        last_error: Exception | None = None
        for attempt, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers={"accept": "application/json"},
                )
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < len(delays) - 1:
                    continue
                raise ExternalServiceError(service, f"网络请求失败：{exc}") from exc

            if response.status_code == 429 or response.status_code >= 500:
                last_error = RuntimeError(f"HTTP {response.status_code}")
                if attempt < len(delays) - 1:
                    continue
            if response.is_error:
                message = f"HTTP {response.status_code}"
                if not sensitive_response:
                    try:
                        body = response.json()
                        if isinstance(body, dict):
                            detail = body.get("detail") or body.get("message")
                            if detail:
                                message += f"：{detail}"
                    except ValueError:
                        pass
                raise ExternalServiceError(service, message)

            try:
                return response.json()
            except ValueError as exc:
                raise ExternalServiceError(service, "响应不是有效 JSON") from exc

        raise ExternalServiceError(service, str(last_error or "请求失败"))

    async def fetch_keywords(self) -> list[str]:
        raw = await self._post_json(
            "热点关键词接口",
            self.settings.external_url("hotspot_api_url"),
            {
                "openId": self.settings.hotspot_open_id,
                "size": self.settings.hotspot_size,
            },
        )
        try:
            response = _HotspotResponse.model_validate(raw)
        except ValidationError as exc:
            raise ExternalServiceError("热点关键词接口", "响应结构无效") from exc
        if response.code != 200:
            raise ExternalServiceError(
                "热点关键词接口", response.message or f"业务状态码 {response.code}"
            )
        if response.data is None:
            raise ExternalServiceError("热点关键词接口", "成功响应缺少 data")
        keywords = list(
            dict.fromkeys(
                record.title.strip()
                for record in response.data.records
                if record.title and record.title.strip()
            )
        )
        return keywords[: self.settings.hotspot_size]

    async def fetch_cookie(self, cookie_type: int) -> str:
        if cookie_type not in {0, 1}:
            raise ValueError("cookie_type 必须是 0 或 1")
        raw = await self._post_json(
            "Cookie 配置接口",
            self.settings.external_url("cookie_api_url"),
            {"type": cookie_type},
            sensitive_response=True,
        )
        try:
            response = _CookieResponse.model_validate(raw)
        except ValidationError as exc:
            raise ExternalServiceError("Cookie 配置接口", "响应结构无效") from exc
        if response.code != 200:
            raise ExternalServiceError(
                "Cookie 配置接口", response.message or f"业务状态码 {response.code}"
            )
        cookie = (response.cookie or "").strip()
        if not cookie:
            raise ExternalServiceError("Cookie 配置接口", "返回了空 Cookie")
        return cookie

    async def upload_rankings(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        raw = await self._post_json(
            "榜单发送接口",
            self.settings.external_url("ranking_api_url"),
            records,
        )
        if isinstance(raw, dict) and "code" in raw and raw.get("code") != 200:
            raise ExternalServiceError(
                "榜单发送接口",
                str(raw.get("message") or f"业务状态码 {raw.get('code')}"),
            )
