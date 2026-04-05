from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_biogrid_interactions_requires_api_key(
    mock_http_client,
):
    mock_http_client.get = AsyncMock()

    with (
        patch("biomcp.tools.extended_databases.get_http_client", return_value=mock_http_client),
        patch("biomcp.tools.extended_databases.os.getenv", return_value=""),
    ):
        from biomcp.tools.extended_databases import get_biogrid_interactions

        result = await get_biogrid_interactions.__wrapped__.__wrapped__.__wrapped__("TP53")

    assert result["gene"] == "TP53"
    assert result["interactions"] == []
    assert "BIOGRID_API_KEY" in result["error"]
    mock_http_client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_biogrid_interactions_uses_configured_api_key(
    mock_http_client,
    mock_http_response,
):
    response = mock_http_response(
        json_data={
            "12345": {
                "OFFICIAL_SYMBOL_A": "TP53",
                "OFFICIAL_SYMBOL_B": "MDM2",
                "EXPERIMENTAL_SYSTEM": "Two-hybrid",
                "EXPERIMENTAL_SYSTEM_TYPE": "physical",
                "PUBMED_ID": "12345678|23456789",
            }
        }
    )
    mock_http_client.get = AsyncMock(return_value=response)

    with (
        patch("biomcp.tools.extended_databases.get_http_client", return_value=mock_http_client),
        patch("biomcp.tools.extended_databases.os.getenv", return_value="test-biogrid-key"),
    ):
        from biomcp.tools.extended_databases import get_biogrid_interactions

        result = await get_biogrid_interactions.__wrapped__.__wrapped__.__wrapped__("TP53")

    assert result["returned"] == 1
    assert result["interactions"][0]["partner_gene"] == "MDM2"
    _, kwargs = mock_http_client.get.await_args
    assert kwargs["params"]["accesskey"] == "test-biogrid-key"


@pytest.mark.asyncio
async def test_get_biogrid_interactions_accepts_integer_pubmed_id(
    mock_http_client,
    mock_http_response,
):
    response = mock_http_response(
        json_data={
            "54321": {
                "OFFICIAL_SYMBOL_A": "TP53",
                "OFFICIAL_SYMBOL_B": "ATM",
                "EXPERIMENTAL_SYSTEM": "Affinity Capture-MS",
                "EXPERIMENTAL_SYSTEM_TYPE": "physical",
                "PUBMED_ID": 12345678,
            }
        }
    )
    mock_http_client.get = AsyncMock(return_value=response)

    with (
        patch("biomcp.tools.extended_databases.get_http_client", return_value=mock_http_client),
        patch("biomcp.tools.extended_databases.os.getenv", return_value="test-biogrid-key"),
    ):
        from biomcp.tools.extended_databases import get_biogrid_interactions

        result = await get_biogrid_interactions.__wrapped__.__wrapped__.__wrapped__("TP53")

    assert result["returned"] == 1
    assert result["interactions"][0]["pubmed_ids"] == ["12345678"]


@pytest.mark.asyncio
async def test_search_metabolomics_caps_remote_title_fan_out(
    mock_http_client,
    mock_http_response,
):
    title_calls: list[str] = []

    async def _fake_get(url: str, headers=None, timeout=None):
        if url.endswith("/study/list"):
            return mock_http_response(
                json_data={"content": [f"MTBLS{i}" for i in range(1, 101)]}
            )
        if "/study/" in url and url.endswith("/title"):
            study_id = url.split("/")[-2]
            title_calls.append(study_id)
            return mock_http_response(json_data={"content": f"TP53 metabolomics {study_id}"})
        raise AssertionError(f"Unexpected URL: {url}")

    mock_http_client.get = AsyncMock(side_effect=_fake_get)

    with patch("biomcp.tools.extended_databases.get_http_client", return_value=mock_http_client):
        from biomcp.tools.extended_databases import search_metabolomics

        result = await search_metabolomics.__wrapped__.__wrapped__.__wrapped__(gene_symbol="TP53")

    assert result["total_found"] == 10
    assert len(title_calls) == 50
    assert title_calls[0] == "MTBLS1"
    assert title_calls[-1] == "MTBLS50"
