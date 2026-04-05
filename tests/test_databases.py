from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_gtex_expression_accepts_list_payload(
    mock_http_client,
    mock_http_response,
):
    response = mock_http_response(
        json_data={
            "data": [
                {
                    "tissueSite": "Lung",
                    "tissueSiteDetailId": "Lung",
                    "data": [12.5, 11.0, 10.5],
                    "median": 11.0,
                    "mean": 11.333,
                },
                {
                    "tissueSite": "Thyroid",
                    "tissueSiteDetailId": "Thyroid",
                    "data": [8.0, 7.5, 7.0],
                },
            ]
        }
    )
    mock_http_client.get = AsyncMock(return_value=response)

    with patch("biomcp.tools.databases.get_http_client", return_value=mock_http_client):
        from biomcp.tools.databases import get_gtex_expression

        result = await get_gtex_expression.__wrapped__.__wrapped__.__wrapped__("EGFR", top_tissues=2)

    assert result["gene"] == "EGFR"
    assert result["total_tissues"] == 2
    assert result["expression_by_tissue"][0]["tissue_site"] == "Lung"


@pytest.mark.asyncio
async def test_get_gtex_expression_falls_back_when_primary_query_is_empty(
    mock_http_client,
    mock_http_response,
):
    empty_expression = mock_http_response(json_data={"data": []})
    gene_lookup = mock_http_response(
        json_data={"data": {"gene": [{"gencodeId": "ENSG00000146648.18"}]}}
    )
    resolved_expression = mock_http_response(
        json_data={
            "data": [
                {
                    "tissueSite": "Lung",
                    "tissueSiteDetailId": "Lung",
                    "data": [20.0, 18.0],
                    "median": 19.0,
                }
            ]
        }
    )
    mock_http_client.get = AsyncMock(side_effect=[empty_expression, gene_lookup, resolved_expression])

    with patch("biomcp.tools.databases.get_http_client", return_value=mock_http_client):
        from biomcp.tools.databases import get_gtex_expression

        result = await get_gtex_expression.__wrapped__.__wrapped__.__wrapped__("EGFR", top_tissues=1)

    assert result["total_tissues"] == 1
    assert result["expression_by_tissue"][0]["tissue_site_detail"] == "Lung"


@pytest.mark.asyncio
async def test_get_disgenet_associations_handles_non_json_response(
    mock_http_client,
):
    class NonJsonResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            raise ValueError("not json")

    mock_http_client.get = AsyncMock(return_value=NonJsonResponse())

    with patch("biomcp.tools.databases.get_http_client", return_value=mock_http_client):
        from biomcp.tools.databases import get_disgenet_associations

        result = await get_disgenet_associations.__wrapped__.__wrapped__.__wrapped__("TP53")

    assert result["gene"] == "TP53"
    assert result["associations"] == []
    assert "non-JSON response" in result["error"]
