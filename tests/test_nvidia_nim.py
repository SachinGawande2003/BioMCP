"""
Tests - NVIDIA NIM tools (mocked HTTP)
======================================
Focused regression coverage for the current hosted NVIDIA API contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = ""
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_predict_structure_boltz2_uses_current_payload_shape(monkeypatch):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=_mock_response(
            {
                "structures": [
                    {
                        "structure": "data_model\n_entry.id model\n",
                        "format": "mmcif",
                        "source": "nvidia-hosted-api",
                    }
                ],
                "metrics": {"total_time_seconds": 1.2},
                "confidence_scores": [0.81],
                "ptm_scores": [0.72],
                "iptm_scores": [0.45],
                "chains_ptm_scores": [0.72],
                "affinities": {},
            }
        )
    )

    with patch("biomcp.tools.nvidia_nim.get_http_client", return_value=mock_client):
        import biomcp.tools.nvidia_nim as nvidia_nim

        monkeypatch.setattr(nvidia_nim, "BOLTZ2_API_KEY", "test-key")
        result = await nvidia_nim.predict_structure_boltz2.__wrapped__.__wrapped__(
            protein_sequences=["MKWVTFISLLLLFSSAYSRG"],
            recycling_steps=1,
            sampling_steps=50,
            diffusion_samples=1,
        )

    payload = mock_client.post.await_args.kwargs["json"]

    assert "polymers" in payload
    assert "sequences" not in payload
    assert "predict_affinity" not in payload
    assert "return_runtime_metrics" not in payload
    assert payload["polymers"][0]["molecule_type"] == "protein"
    assert result["scores"]["confidence"] == 0.81
    assert result["structure"]["format"] == "mmcif"


@pytest.mark.asyncio
async def test_generate_dna_evo2_uses_enable_logits_field(monkeypatch):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        return_value=_mock_response(
            {
                "sequence": "AC",
                "logits": [[0.1, 0.4, 0.7]],
                "sampled_probs": None,
            }
        )
    )

    with patch("biomcp.tools.nvidia_nim.get_http_client", return_value=mock_client):
        import biomcp.tools.nvidia_nim as nvidia_nim

        monkeypatch.setattr(nvidia_nim, "EVO2_API_KEY", "test-key")
        result = await nvidia_nim.generate_dna_evo2.__wrapped__.__wrapped__(
            sequence="ATGGCGTACGATCGTACGTA",
            num_tokens=2,
            enable_logits=True,
        )

    payload = mock_client.post.await_args.kwargs["json"]

    assert payload["enable_logits"] is True
    assert "enable_logits_reporting" not in payload
    assert result["generations"][0]["generated_sequence"] == "AC"


@pytest.mark.asyncio
async def test_score_sequence_evo2_returns_proxy_scores(monkeypatch):
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[
            _mock_response({"sequence": "C", "logits": [[0.1, 0.8, 0.2]]}),
            _mock_response({"sequence": "G", "logits": [[0.1, 0.6, 0.2]]}),
        ]
    )

    with patch("biomcp.tools.nvidia_nim.get_http_client", return_value=mock_client):
        import biomcp.tools.nvidia_nim as nvidia_nim

        monkeypatch.setattr(nvidia_nim, "EVO2_API_KEY", "test-key")
        result = await nvidia_nim.score_sequence_evo2.__wrapped__.__wrapped__(
            wildtype_sequence="ATGGC",
            variant_sequence="ATGGA",
        )

    requests = [call.kwargs["json"] for call in mock_client.post.await_args_list]

    assert all(request["enable_logits"] is True for request in requests)
    assert result["wildtype_score"] == 0.8
    assert result["variant_score"] == 0.6
    assert result["delta_score"] == -0.2
    assert result["wildtype_next_token"] == "C"
    assert result["variant_next_token"] == "G"
