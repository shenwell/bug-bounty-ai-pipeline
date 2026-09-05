"""Tests for post-select contract link enrichment."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from portfolio.common.config import AppConfig
from portfolio.common.models import Contract
from portfolio.discovery.link_enrichment import (
    classify_reference,
    enrich_contract_links,
    extract_urls_from_contract,
    write_references_markdown,
)


def test_extract_urls_from_tabs_and_markdown():
    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        tab_sections={
            "Description": "API docs: https://api.example.com/swagger.json",
            "Scope": "See [OpenAPI](https://docs.example.com/openapi) for details.",
        },
        acceptance_criteria="https://bugbounty.standoff365.com/programs/demo should be skipped",
    )
    urls = extract_urls_from_contract(contract)
    found = {u for u, _, _ in urls}
    assert "https://api.example.com/swagger.json" in found
    assert "https://docs.example.com/openapi" in found
    assert not any("standoff365.com/programs" in u for u in found)


def test_classify_reference():
    assert classify_reference("https://api.example.com/swagger-ui") == "api_docs"
    assert classify_reference("https://github.com/org/repo") == "documentation"
    assert classify_reference("https://cdn.example.com/guide.pdf") == "generic"


def test_write_references_markdown(tmp_path):
    contract = Contract(program_id="demo", slug="demo", name="Demo")
    from portfolio.common.models import ExternalReference

    refs = [
        ExternalReference(
            url="https://api.example.com/swagger.json",
            ref_type="api_spec",
            status_code=200,
            preview='{"openapi": "3.0.0"}',
            in_scope=True,
        )
    ]
    path = tmp_path / "references.md"
    write_references_markdown(path, contract, refs)
    text = path.read_text(encoding="utf-8")
    assert "api_spec" in text
    assert "swagger.json" in text


def test_enrich_contract_links_fetch(tmp_path):
    config = AppConfig()
    config.data.dossiers_dir = str(tmp_path / "dossiers")
    config.data.artifacts_dir = str(tmp_path / "artifacts")
    config.recon.fetch_contract_links = True
    config.recon.max_contract_links = 5

    contract = Contract(
        program_id="demo",
        slug="demo",
        name="Demo",
        scope=["api.example.com"],
        tab_sections={"Description": "Swagger: https://api.example.com/swagger.json"},
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.content = b'{"openapi":"3.0.0","paths":{"/health":{}}}'

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("portfolio.discovery.link_enrichment.httpx.AsyncClient", return_value=mock_client):
        refs = asyncio.run(enrich_contract_links(config, contract))

    assert len(refs) == 1
    assert refs[0].status_code == 200
    assert "openapi" in refs[0].preview
    refs_file = tmp_path / "dossiers" / "demo" / "references.json"
    assert refs_file.exists()
    saved = json.loads(refs_file.read_text(encoding="utf-8"))
    assert saved[0]["url"] == "https://api.example.com/swagger.json"

