"""Small in-memory CMS used as a deterministic sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CMSFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Page:
    slug: str
    title: str
    body: str = ""
    status: str = "draft"
    metadata: dict[str, Any] = field(default_factory=dict)
    media: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "metadata": dict(self.metadata),
            "media": [dict(item) for item in self.media],
        }


class CMS:
    """A tiny CMS with auth, conflicts, and injectable tool failures."""

    def __init__(self, token: str = "test-token") -> None:
        self.token = token
        self.pages: dict[str, Page] = {}
        self.media: dict[str, dict[str, Any]] = {}
        self.faults: dict[str, list[str]] = {}

    def reset(self) -> None:
        self.pages.clear()
        self.media.clear()
        self.faults.clear()

    def seed_page(
        self,
        title: str,
        slug: str,
        *,
        status: str = "published",
        body: str = "",
        metadata: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
    ) -> None:
        self.pages[slug] = Page(
            slug=slug,
            title=title,
            body=body,
            status=status,
            metadata=dict(metadata or {}),
            media=[dict(item) for item in media or []],
        )

    def inject_fault(self, tool: str, code: str) -> None:
        self.faults.setdefault(tool, []).append(code)

    def _check_token(self, token: str | None) -> None:
        if token != self.token:
            raise CMSFailure("auth_required")

    def _maybe_fault(self, tool: str) -> None:
        queue = self.faults.get(tool) or []
        if queue:
            code = queue.pop(0)
            raise CMSFailure(code)

    def create_draft(
        self,
        token: str | None,
        title: str,
        slug: str,
        *,
        body: str = "",
        metadata: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._check_token(token)
        self._maybe_fault("cms_create_draft")
        if slug in self.pages:
            raise CMSFailure("slug_conflict")
        self.pages[slug] = Page(
            slug=slug,
            title=title,
            body=body,
            status="draft",
            metadata=dict(metadata or {}),
            media=[dict(item) for item in media or []],
        )
        return self.pages[slug].to_dict()

    def update_draft(
        self, token: str | None, slug: str, **fields: Any
    ) -> dict[str, Any]:
        self._check_token(token)
        self._maybe_fault("cms_update_draft")
        page = self.pages.get(slug)
        if page is None:
            raise CMSFailure("page_not_found")
        for key in ("title", "body", "status", "metadata", "media"):
            if key in fields and fields[key] is not None:
                setattr(page, key, fields[key])
        return page.to_dict()

    def upload_media(
        self, token: str | None, filename: str, alt: str
    ) -> dict[str, Any]:
        self._check_token(token)
        self._maybe_fault("cms_upload_media")
        item = {
            "filename": filename,
            "alt": alt,
            "url": f"/media/{filename}",
        }
        self.media[filename] = item
        return dict(item)

    def publish(self, token: str | None, slug: str) -> dict[str, Any]:
        self._check_token(token)
        self._maybe_fault("cms_publish")
        page = self.pages.get(slug)
        if page is None:
            raise CMSFailure("page_not_found")
        page.status = "published"
        return page.to_dict()

    def get_page(self, slug: str) -> dict[str, Any] | None:
        page = self.pages.get(slug)
        return page.to_dict() if page else None

    def list_pages(self) -> list[dict[str, Any]]:
        return [
            {
                "slug": page.slug,
                "title": page.title,
                "status": page.status,
            }
            for page in sorted(self.pages.values(), key=lambda item: item.slug)
        ]

    def call(self, tool: str, *, token: str | None = None, **kwargs: Any) -> dict[str, Any]:
        try:
            if tool == "cms_list_pages":
                return {"ok": True, "pages": self.list_pages()}
            if tool == "cms_get_page":
                page = self.get_page(str(kwargs.get("slug") or ""))
                return {"ok": True, "page": page}
            if tool == "cms_create_draft":
                page = self.create_draft(token, **kwargs)
                return {"ok": True, "page": page}
            if tool == "cms_update_draft":
                page = self.update_draft(token, **kwargs)
                return {"ok": True, "page": page}
            if tool == "cms_upload_media":
                item = self.upload_media(token, **kwargs)
                return {"ok": True, "media": item}
            if tool == "cms_publish":
                page = self.publish(token, **kwargs)
                return {"ok": True, "page": page}
            return {"ok": False, "error": "unknown_tool"}
        except CMSFailure as error:
            return {"ok": False, "error": error.code}
