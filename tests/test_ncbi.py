"""
Tests — NCBI Tools (Mocked HTTP)
==================================
Unit tests for PubMed search, Gene info, and BLAST.
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── PubMed Search ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_pubmed_parses_results(mock_http_client, mock_http_response):
    """search_pubmed should parse esearch + efetch XML into structured articles."""
    # Mock esearch response (returns IDs)
    esearch_resp = mock_http_response(
        json_data={"esearchresult": {"idlist": ["39000001", "39000002"], "count": "2"}}
    )
    # Mock efetch response (returns XML)
    efetch_resp = mock_http_response(text="""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>39000001</PMID>
      <Article>
        <ArticleTitle>CRISPR TP53 Correction</ArticleTitle>
        <Abstract><AbstractText>A breakthrough study.</AbstractText></Abstract>
        <Journal><Title>Nature</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <AuthorList><Author><LastName>Smith</LastName><ForeName>J</ForeName></Author></AuthorList>
        <ArticleIdList><ArticleId IdType="doi">10.1038/test</ArticleId></ArticleIdList>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>""")

    mock_http_client.get = AsyncMock(side_effect=[esearch_resp, efetch_resp])

    with patch("biomcp.tools.ncbi.get_http_client", return_value=mock_http_client):
        from biomcp.tools.ncbi import search_pubmed
        # Clear any cached result
        result = await search_pubmed.__wrapped__.__wrapped__.__wrapped__("TP53 CRISPR", max_results=5)

    assert result["total_found"] == 2
    assert len(result["articles"]) >= 1
    assert result["articles"][0]["pmid"] == "39000001"


# ── Gene Info ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_gene_info_parses_response(mock_http_client, mock_http_response):
    """get_gene_info should return structured gene data from NCBI Gene."""
    esearch_resp = mock_http_response(
        json_data={"esearchresult": {"idlist": ["7157"], "count": "1"}}
    )
    esummary_resp = mock_http_response(
        json_data={
            "result": {
                "uids": ["7157"],
                "7157": {
                    "uid": "7157",
                    "name": "TP53",
                    "description": "tumor protein p53",
                    "organism": {"scientificname": "Homo sapiens"},
                    "chromosome": "17",
                    "maplocation": "17p13.1",
                    "summary": "This gene encodes a tumor suppressor protein.",
                    "otheraliases": "p53, LFS1",
                    "genomicinfo": [{"chrloc": "17", "chrstart": 7668421, "chrstop": 7687490}],
                },
            }
        }
    )

    mock_http_client.get = AsyncMock(side_effect=[esearch_resp, esummary_resp])

    with patch("biomcp.tools.ncbi.get_http_client", return_value=mock_http_client):
        from biomcp.tools.ncbi import get_gene_info
        result = await get_gene_info.__wrapped__.__wrapped__.__wrapped__("TP53")

    assert result["symbol"] == "TP53"
    assert result["chromosome"] == "17"
    assert "tumor" in result.get("summary", "").lower()


@pytest.mark.asyncio
async def test_run_blast_returns_pending_when_ncbi_stays_waiting(mock_http_client, mock_http_response):
    submit_resp = mock_http_response(text="RID = TEST123\nRTOE = 1\n")
    poll_resp = mock_http_response(text="Status=WAITING\n")

    mock_http_client.post = AsyncMock(return_value=submit_resp)
    mock_http_client.get = AsyncMock(side_effect=[poll_resp] * 24)

    with patch("biomcp.tools.ncbi.get_http_client", return_value=mock_http_client):
        with patch("biomcp.tools.ncbi.asyncio.sleep", new=AsyncMock()):
            from biomcp.tools.ncbi import run_blast

            result = await run_blast.__wrapped__.__wrapped__(
                "MTEYKLVVVGAGGVGKSALTIQLIQNHF",
                program="blastp",
                database="swissprot",
                max_hits=2,
            )

    assert result["status"] == "pending"
    assert result["rid"] == "TEST123"
    assert result["hits"] == []


def test_blast_zip_result_parses_current_ncbi_format():
    """BLAST parser should accept the current ZIP-wrapped JSON result format."""
    blast_json = {
        "BlastOutput2": [
            {
                "report": {
                    "results": {
                        "search": {
                            "query_len": 42,
                            "hits": [
                                {
                                    "description": [
                                        {
                                            "accession": "P04637",
                                            "title": "Cellular tumor antigen p53",
                                            "taxid": 9606,
                                            "sciname": "Homo sapiens",
                                        }
                                    ],
                                    "hsps": [
                                        {
                                            "align_len": 42,
                                            "identity": 40,
                                            "query_from": 1,
                                            "query_to": 42,
                                            "evalue": 1e-20,
                                            "bit_score": 120.0,
                                            "gaps": 0,
                                            "positive": 41,
                                        }
                                    ],
                                }
                            ],
                            "stat": {"db_num": 1},
                        }
                    }
                }
            }
        ]
    }

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_handle:
        zip_handle.writestr("blast_result.json", json.dumps(blast_json))

    response = MagicMock()
    response.content = archive.getvalue()
    response.text = ""

    from biomcp.tools.ncbi import _extract_blast_result_text, _parse_blast_json2

    raw = _extract_blast_result_text(response, "RID123")
    result = _parse_blast_json2(raw, "RID123", "blastp", "swissprot")

    assert result["rid"] == "RID123"
    assert result["total_hits"] == 1
    assert result["hits"][0]["accession"] == "P04637"


def test_blast_zip_manifest_resolves_referenced_result_file():
    """BLAST parser should resolve manifest-style ZIP archives returned by NCBI."""
    blast_json = {
        "BlastOutput2": [
            {
                "report": {
                    "results": {
                        "search": {
                            "query_len": 15,
                            "hits": [
                                {
                                    "description": [{"accession": "P00533", "title": "EGFR"}],
                                    "hsps": [
                                        {
                                            "align_len": 15,
                                            "identity": 14,
                                            "query_from": 1,
                                            "query_to": 15,
                                            "evalue": 1e-10,
                                            "bit_score": 80.0,
                                            "gaps": 0,
                                            "positive": 15,
                                        }
                                    ],
                                }
                            ],
                            "stat": {"db_num": 1},
                        }
                    }
                }
            }
        ]
    }
    manifest = {"BlastJSON": [{"File": "RID123_1.json"}]}

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_handle:
        zip_handle.writestr("index.json", json.dumps(manifest))
        zip_handle.writestr("RID123_1.json", json.dumps(blast_json))

    response = MagicMock()
    response.content = archive.getvalue()
    response.text = ""

    from biomcp.tools.ncbi import _extract_blast_result_text, _parse_blast_json2

    raw = _extract_blast_result_text(response, "RID123")
    result = _parse_blast_json2(raw, "RID123", "blastp", "swissprot")

    assert result["total_hits"] == 1
    assert result["hits"][0]["accession"] == "P00533"


def test_blast_parser_accepts_mapping_blastoutput2_shape():
    blast_json = {
        "BlastOutput2": {
            "report": {
                "results": {
                    "search": {
                        "query_len": 21,
                        "hits": [
                            {
                                "description": [{"accession": "P01116", "title": "KRAS"}],
                                "hsps": [
                                    {
                                        "align_len": 21,
                                        "identity": 21,
                                        "query_from": 1,
                                        "query_to": 21,
                                        "evalue": 1e-12,
                                        "bit_score": 90.0,
                                        "gaps": 0,
                                        "positive": 21,
                                    }
                                ],
                            }
                        ],
                        "stat": {"db_num": 1},
                    }
                }
            }
        }
    }

    from biomcp.tools.ncbi import _parse_blast_json2

    result = _parse_blast_json2(json.dumps(blast_json), "RID999", "blastp", "swissprot")

    assert result["total_hits"] == 1
    assert result["hits"][0]["accession"] == "P01116"


# ── Integration (Network Required) ──────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_pubmed_search_live():
    from biomcp.tools.ncbi import search_pubmed
    result = await search_pubmed("TP53 tumor suppressor", max_results=3)
    assert result["total_found"] > 0
    assert len(result["articles"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gene_info_live():
    from biomcp.tools.ncbi import get_gene_info
    result = await get_gene_info("TP53")
    assert result.get("symbol", "").upper() in ("TP53", "P53")
