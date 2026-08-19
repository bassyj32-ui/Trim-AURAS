"""Public share-token tests: stateless HMAC tokens + the public endpoints
that make shared clips watchable WITHOUT a login (YouTube-"unlisted" model)."""

import pytest
from httpx import AsyncClient

from app.share import make_share_token, verify_share_token


class TestShareToken:
    def test_token_is_deterministic(self):
        assert make_share_token(42) == make_share_token(42)

    def test_token_differs_per_clip(self):
        assert make_share_token(42) != make_share_token(43)

    def test_verify_accepts_valid_token(self):
        token = make_share_token(7)
        assert verify_share_token(7, token) is True

    def test_verify_rejects_wrong_token(self):
        token = make_share_token(7)
        assert verify_share_token(8, token) is False

    def test_verify_rejects_missing_or_garbage(self):
        assert verify_share_token(7, None) is False
        assert verify_share_token(7, "") is False
        assert verify_share_token(7, "ta1garbage") is False


class TestPublicClipEndpoints:
    @pytest.mark.asyncio
    async def test_public_meta_requires_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/api/public/clips/{sample_clip.id}")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_public_meta_wrong_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/api/public/clips/{sample_clip.id}?t=ta1wrongtoken")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_public_meta_unknown_clip(self, client: AsyncClient):
        token = make_share_token(999)
        res = await client.get(f"/api/public/clips/999?t={token}")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_public_meta_valid_token(self, client: AsyncClient, sample_clip):
        token = make_share_token(sample_clip.id)
        res = await client.get(f"/api/public/clips/{sample_clip.id}?t={token}")
        assert res.status_code == 200
        data = res.json()
        assert data["clip_id"] == sample_clip.id
        assert data["titles"]["curiosity"] == "Why This Works"
        assert data["viral_score"] == 85
        # Internal storage paths must never leak on the public shape
        assert "r2_url" not in data
        assert "r2_key" not in data
        assert f"/api/public/clips/{sample_clip.id}/download" in data["stream_url"]
        assert f"/api/public/clips/{sample_clip.id}/poster" in data["poster_url"]

    @pytest.mark.asyncio
    async def test_public_download_valid_token(self, client: AsyncClient, sample_clip):
        token = make_share_token(sample_clip.id)
        res = await client.get(f"/api/public/clips/{sample_clip.id}/download?t={token}")
        # No real file in tests, so it falls back to a download_url payload.
        assert res.status_code == 200
        assert "download_url" in res.json()

    @pytest.mark.asyncio
    async def test_public_download_wrong_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/api/public/clips/{sample_clip.id}/download?t=bad")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_public_poster_wrong_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/api/public/clips/{sample_clip.id}/poster?t=bad")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_public_poster_valid_token_no_file(self, client: AsyncClient, sample_clip):
        # No real MP4 in tests -> no poster can be extracted -> 404 (not an auth error)
        token = make_share_token(sample_clip.id)
        res = await client.get(f"/api/public/clips/{sample_clip.id}/poster?t={token}")
        assert res.status_code == 404


class TestSharePage:
    @pytest.mark.asyncio
    async def test_share_page_requires_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/clip/{sample_clip.id}")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_share_page_wrong_token(self, client: AsyncClient, sample_clip):
        res = await client.get(f"/clip/{sample_clip.id}?t=nope")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_share_page_renders_og_tags(self, client: AsyncClient, sample_clip):
        token = make_share_token(sample_clip.id)
        res = await client.get(f"/clip/{sample_clip.id}?t={token}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/html")
        body = res.text
        assert 'og:title' in body
        assert 'Why This Works' in body
        assert f'/api/public/clips/{sample_clip.id}/poster?t={token}' in body
        assert f'/api/public/clips/{sample_clip.id}/download?t={token}' in body
        assert "twitter:card" in body
