import pytest
from httpx import AsyncClient


class TestTemplatesAPI:
    @pytest.mark.asyncio
    async def test_list_templates(self, client: AsyncClient):
        res = await client.get("/api/templates")
        assert res.status_code == 200
        templates = res.json()
        assert isinstance(templates, list)
        assert len(templates) >= 1
        
        t = templates[0]
        assert "id" in t
        assert "name" in t
        assert "description" in t

    @pytest.mark.asyncio
    async def test_template_ids_match_known(self, client: AsyncClient):
        res = await client.get("/api/templates")
        templates = res.json()
        ids = {t["id"] for t in templates}
        expected = {"blurpad_v1", "podcast_split_v1", "gaming_neon_v1", "mrbeast_energy_v1", "brand_bold_v1", "retro_vhs_v1"}
        assert expected.issubset(ids)


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "modal_flag" in data
        assert "engine_url" in data