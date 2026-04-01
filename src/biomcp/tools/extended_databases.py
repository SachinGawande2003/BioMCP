"""
BioMCP — Tier 2 Extended Databases
=====================================
Seven additional databases filling critical research gaps:

  get_biogrid_interactions    — BioGRID: 2M+ curated protein-protein
                                interactions across genetic, physical,
                                and chemical methods.

  search_orphan_diseases      — Orphanet: 6,000+ rare diseases with
                                gene associations, prevalence data,
                                and clinical classification.

  get_tcga_expression         — TCGA via GDC API: actual tumor RNA-seq
                                from thousands of patients across 33
                                cancer types. Not cell lines — real tumors.

  search_cellmarker           — CellMarker 2.0: validated cell type
                                markers for 1,000+ cell types across
                                tissues. Critical for scRNA-seq annotation.

  get_encode_regulatory       — ENCODE: promoters, enhancers, CTCF sites,
                                TF binding from ChIP-seq / ATAC-seq.

  search_metabolomics         — MetaboLights: metabolite-gene-disease
                                connections from curated metabolomics studies.

  get_ucsc_splice_variants    — UCSC Genome Browser API: alternative
                                splicing isoforms, UTR annotations,
                                disease-relevant splice variants.

APIs:
  BioGRID      https://webservice.thebiogrid.org/
  Orphanet     https://api.orphacode.org/
  GDC (TCGA)   https://api.gdc.cancer.gov/
  CellMarker   http://xteam.xbio.top/CellMarker/
  ENCODE       https://www.encodeproject.org/search/
  MetaboLights https://www.ebi.ac.uk/metabolights/ws/
  UCSC         https://api.genome.ucsc.edu/
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from loguru import logger

from biomcp.utils import (
    BioValidator,
    cached,
    get_http_client,
    rate_limited,
    with_retry,
)

# BioGRID requires a free API key — get one at https://webservice.thebiogrid.org/
_BIOGRID_KEY = os.getenv("BIOGRID_API_KEY", "")

_BIOGRID_BASE    = "https://webservice.thebiogrid.org"
_ORPHANET_BASE   = "https://api.orphacode.org/EN/ClinicalEntity"
_GDC_BASE        = "https://api.gdc.cancer.gov"
_ENCODE_BASE     = "https://www.encodeproject.org"
_METABOLIGHTS    = "https://www.ebi.ac.uk/metabolights/ws"
_UCSC_BASE       = "https://api.genome.ucsc.edu"


# ─────────────────────────────────────────────────────────────────────────────
# BioGRID — curated protein-protein interactions
# ─────────────────────────────────────────────────────────────────────────────

@cached("biogrid")
@rate_limited("default")
@with_retry(max_attempts=3)
async def get_biogrid_interactions(
    gene_symbol:    str,
    interaction_type: str = "physical",
    min_publications: int = 1,
    max_results:    int = 25,
    include_genetic: bool = False,
) -> dict[str, Any]:
    """
    Retrieve curated protein-protein interactions from BioGRID.

    BioGRID contains 2M+ manually curated interactions from primary
    literature. Unlike STRING (prediction-based), BioGRID interactions
    are directly extracted from experimental papers.

    Args:
        gene_symbol:      HGNC gene symbol (e.g. 'TP53', 'EGFR').
        interaction_type: 'physical' | 'genetic' | 'all'. Default 'physical'.
        min_publications: Minimum publication support. Default 1.
        max_results:      Interactions to return (1–100). Default 25.
        include_genetic:  Include genetic interactions (SL, suppression). Default False.

    Returns:
        {
          gene, biogrid_id, interaction_count,
          interactions: [{
            partner_gene, partner_official_symbol, partner_organism,
            experimental_system, experimental_system_type,
            publication_count, pubmed_ids, interaction_type,
            modification, qualifications, biogrid_interaction_id
          }],
          network_stats: { physical_count, genetic_count, hub_score }
        }

    Interaction types:
        Co-localization, Co-purification, Reconstituted Complex,
        Two-hybrid (Y2H), FRET, Co-fractionation, Affinity Capture-MS, etc.
    """
    gene_symbol = BioValidator.validate_gene_symbol(gene_symbol)
    max_results = BioValidator.clamp_int(max_results, 1, 100, "max_results")
    client      = await get_http_client()

    params: dict[str, Any] = {
        "searchNames":   True,
        "geneList":      gene_symbol,
        "organism":      9606,              # Homo sapiens
        "searchbiogridids": False,
        "includeInteractors":    True,
        "includeInteractorIds":  True,
        "includeEvidence":       True,
        "includePubmedId":       True,
        "includeOfficialSymbol": True,
        "taxId":         9606,
        "max":           max_results,
        "format":        "json",
    }

    if _BIOGRID_KEY:
        params["accesskey"] = _BIOGRID_KEY
    else:
        # Without key, use the public endpoint with limited results
        params["accesskey"] = "BIOGRID-7678"   # public demo key

    if interaction_type != "all":
        params["interSpeciesExcluded"] = True
        if interaction_type == "physical":
            params["includeEvidence"] = "Co-purification|Affinity Capture-MS|Two-hybrid|Co-localization"

    resp = await client.get(
        f"{_BIOGRID_BASE}/interactions/",
        params=params,
        headers={"Accept": "application/json"},
    )

    if resp.status_code == 403:
        return {
            "gene":  gene_symbol,
            "error": (
                "BioGRID requires a free API key for full access. "
                "Register at https://webservice.thebiogrid.org/ and add "
                "BIOGRID_API_KEY to your .env file."
            ),
            "interactions": [],
        }
    if resp.status_code == 404:
        return {"gene": gene_symbol, "interactions": [], "interaction_count": 0}

    resp.raise_for_status()
    data = resp.json()

    interactions: list[dict[str, Any]] = []
    physical_count = 0
    genetic_count  = 0

    for iid, record in list(data.items())[:max_results]:
        if not isinstance(record, dict):
            continue

        gene_a = record.get("OFFICIAL_SYMBOL_A", "")
        gene_b = record.get("OFFICIAL_SYMBOL_B", "")
        partner = gene_b if gene_a.upper() == gene_symbol else gene_a

        exp_system = record.get("EXPERIMENTAL_SYSTEM", "")
        exp_type   = record.get("EXPERIMENTAL_SYSTEM_TYPE", "physical")
        pubmed_ids = [str(p) for p in (record.get("PUBMED_ID", "") or "").split("|") if p]

        if exp_type == "physical":
            physical_count += 1
        else:
            genetic_count += 1
            if not include_genetic and interaction_type != "all":
                continue

        interactions.append({
            "partner_gene":              partner,
            "partner_entrez_id":         record.get("ENTREZ_GENE_B" if gene_a.upper() == gene_symbol else "ENTREZ_GENE_A", ""),
            "experimental_system":       exp_system,
            "experimental_system_type":  exp_type,
            "publication_count":         len(pubmed_ids),
            "pubmed_ids":                pubmed_ids[:5],
            "pubmed_urls":               [f"https://pubmed.ncbi.nlm.nih.gov/{p}/" for p in pubmed_ids[:3]],
            "interaction_type":          exp_type,
            "modification":              record.get("MODIFICATION", ""),
            "qualifications":            record.get("QUALIFICATIONS", ""),
            "throughput":                record.get("THROUGHPUT", ""),
            "biogrid_interaction_id":    iid,
            "biogrid_url":               f"https://thebiogrid.org/interaction/{iid}",
        })

    # Hub score: high degree = central hub protein
    hub_score = min(1.0, len(interactions) / 100)

    return {
        "gene":              gene_symbol,
        "organism":          "Homo sapiens",
        "interaction_count": len(data),
        "returned":          len(interactions),
        "interactions":      interactions,
        "network_stats": {
            "physical_interactions": physical_count,
            "genetic_interactions":  genetic_count,
            "hub_score":             round(hub_score, 2),
            "hub_classification": (
                "Major hub protein (>50 interactions)" if hub_score > 0.5 else
                "Intermediate hub (10–50)"             if hub_score > 0.1 else
                "Peripheral node (<10 interactions)"
            ),
        },
        "biogrid_gene_url": f"https://thebiogrid.org/search.php?search={gene_symbol}&organism=9606",
        "note": (
            "BioGRID interactions are manually curated from primary literature. "
            "All interactions have direct experimental evidence."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orphanet — rare disease database
# ─────────────────────────────────────────────────────────────────────────────

@cached("orphanet")
@rate_limited("default")
@with_retry(max_attempts=3)
async def search_orphan_diseases(
    gene_symbol:  str = "",
    disease_name: str = "",
    max_results:  int = 15,
) -> dict[str, Any]:
    """
    Search Orphanet for rare diseases associated with a gene or disease name.

    Orphanet is the reference portal for rare diseases — 6,000+ diseases
    with validated gene associations, prevalence estimates, inheritance
    patterns, and clinical classification. Critical for unmet medical
    needs analysis and drug repurposing into rare disease indications.

    Args:
        gene_symbol:  HGNC gene symbol to find associated rare diseases.
        disease_name: Disease name or keyword (alternative to gene_symbol).
        max_results:  Diseases to return (1–50). Default 15.

    Returns:
        {
          query, total_found,
          diseases: [{
            orpha_code, disease_name, disease_type,
            prevalence, inheritance_patterns,
            associated_genes, icd10_codes,
            orphanet_url, clinical_description_url
          }]
        }
    """
    if not gene_symbol and not disease_name:
        raise ValueError("Provide either gene_symbol or disease_name.")

    max_results = BioValidator.clamp_int(max_results, 1, 50, "max_results")
    client      = await get_http_client()

    diseases: list[dict[str, Any]] = []

    if gene_symbol:
        gene_symbol = BioValidator.validate_gene_symbol(gene_symbol)

        # Query via NCBI Gene → OMIM → cross-reference with Orphanet
        # Orphanet REST API: search by gene symbol
        resp = await client.get(
            f"https://api.orphacode.org/EN/ClinicalEntity/ApproximateName/{gene_symbol}",
            headers={"accept": "application/json"},
        )

        if resp.status_code == 200:
            data = resp.json()
            for item in (data if isinstance(data, list) else [data])[:max_results]:
                orpha_code = item.get("OrphaCode", "")
                name       = item.get("Preferred term", item.get("Name", ""))
                if not orpha_code or not name:
                    continue
                diseases.append({
                    "orpha_code":              str(orpha_code),
                    "disease_name":            name,
                    "disease_type":            item.get("DisorderType", {}).get("Name", ""),
                    "prevalence":              _extract_prevalence(item),
                    "inheritance_patterns":    _extract_inheritance(item),
                    "icd10_codes":             [
                        x.get("Code", "") for x in item.get("ICD10", [])
                    ],
                    "orphanet_url":            f"https://www.orpha.net/consor/cgi-bin/OC_Exp.php?Expert={orpha_code}",
                    "clinical_description":    f"https://www.orpha.net/consor/cgi-bin/Disease_Search.php?lng=EN&data_id={orpha_code}",
                })

        if not diseases:
            # Fallback: use Orphanet text search via their public endpoint
            fallback = await client.get(
                "https://api.orphacode.org/EN/ClinicalEntity/ApproximateName/" + gene_symbol,
                headers={"accept": "application/json"},
            )
            if fallback.status_code == 200:
                fb_data = fallback.json()
                for item in (fb_data if isinstance(fb_data, list) else [])[:max_results]:
                    orpha_code = item.get("OrphaCode", "")
                    name       = item.get("Preferred term", "")
                    if orpha_code and name:
                        diseases.append({
                            "orpha_code":   str(orpha_code),
                            "disease_name": name,
                            "orphanet_url": f"https://www.orpha.net/consor/cgi-bin/OC_Exp.php?Expert={orpha_code}",
                        })

    if disease_name and not diseases:
        # Search by disease name
        resp = await client.get(
            f"https://api.orphacode.org/EN/ClinicalEntity/ApproximateName/{disease_name}",
            headers={"accept": "application/json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in (data if isinstance(data, list) else [])[:max_results]:
                orpha_code = item.get("OrphaCode", "")
                name       = item.get("Preferred term", item.get("Name", ""))
                if orpha_code and name:
                    diseases.append({
                        "orpha_code":   str(orpha_code),
                        "disease_name": name,
                        "disease_type": item.get("DisorderType", {}).get("Name", ""),
                        "orphanet_url": f"https://www.orpha.net/consor/cgi-bin/OC_Exp.php?Expert={orpha_code}",
                    })

    if not diseases:
        return {
            "query":        gene_symbol or disease_name,
            "total_found":  0,
            "diseases":     [],
            "note":         (
                "No Orphanet data found. Try the Orphanet portal directly: "
                f"https://www.orpha.net/consor/cgi-bin/Disease_Search.php?lng=EN&data_id=&Disease_Disease_Search_diseaseGroup={gene_symbol or disease_name}"
            ),
            "orphanet_search_url": (
                f"https://www.orpha.net/consor/cgi-bin/Disease_Search.php?lng=EN"
                f"&data_id=&Disease_Disease_Search_diseaseGroup={gene_symbol or disease_name}"
            ),
        }

    return {
        "query":        gene_symbol or disease_name,
        "total_found":  len(diseases),
        "diseases":     diseases[:max_results],
        "orphanet_portal": "https://www.orpha.net",
        "note": (
            "Orphanet is the reference database for rare diseases. "
            "All entries are validated by expert panels."
        ),
    }


def _extract_prevalence(item: dict) -> str:
    prev = item.get("Prevalence", [])
    if isinstance(prev, list) and prev:
        return prev[0].get("PrevalenceClass", {}).get("Name", "Unknown")
    return "Unknown"


def _extract_inheritance(item: dict) -> list[str]:
    patterns = item.get("TypeOfInheritance", [])
    if isinstance(patterns, list):
        return [p.get("Name", "") for p in patterns if p.get("Name")]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# TCGA via GDC API — real tumor RNA-seq expression
# ─────────────────────────────────────────────────────────────────────────────

@cached("tcga")
@rate_limited("default")
@with_retry(max_attempts=3)
async def get_tcga_expression(
    gene_symbol:  str,
    cancer_type:  str = "",
    max_cases:    int = 10,
) -> dict[str, Any]:
    """
    Retrieve gene expression data from TCGA tumor samples via GDC API.

    Unlike GTEx (healthy tissue) and GEO (heterogeneous datasets), this
    returns RNA-seq from actual patient tumor samples with clinical metadata
    — the gold standard for cancer genomics.

    Args:
        gene_symbol: HGNC gene symbol (e.g. 'TP53', 'KRAS', 'EGFR').
        cancer_type: TCGA project code (e.g. 'TCGA-LUAD', 'TCGA-BRCA').
                     Leave empty for pan-cancer overview.
        max_cases:   Cases to sample (1–50). Default 10.

    Returns:
        {
          gene, cancer_type,
          available_projects: [...TCGA project codes...],
          expression_files: [{
            file_id, case_id, project,
            sample_type, file_size, data_format
          }],
          clinical_summary: { ... },
          gdc_gene_url,
          download_instructions
        }

    TCGA Project Codes (common):
        TCGA-BRCA (breast), TCGA-LUAD (lung adeno),
        TCGA-COAD (colon), TCGA-GBM (glioblastoma),
        TCGA-PRAD (prostate), TCGA-OV (ovarian)
    """
    gene_symbol = BioValidator.validate_gene_symbol(gene_symbol)
    max_cases   = BioValidator.clamp_int(max_cases, 1, 50, "max_cases")
    client      = await get_http_client()

    # ── Step 1: Find available TCGA files for this gene ───────────────────────
    file_filters: dict[str, Any] = {
        "op": "and",
        "content": [
            {"op": "=", "content": {"field": "cases.project.program.name", "value": "TCGA"}},
            {"op": "=", "content": {"field": "data_type", "value": "Gene Expression Quantification"}},
            {"op": "=", "content": {"field": "data_format", "value": "TSV"}},
            {"op": "=", "content": {"field": "experimental_strategy", "value": "RNA-Seq"}},
            {"op": "=", "content": {"field": "analysis.workflow_type", "value": "STAR - Counts"}},
        ]
    }

    if cancer_type:
        file_filters["content"].append({
            "op": "=",
            "content": {"field": "cases.project.project_id", "value": cancer_type.upper()}
        })

    files_resp = await client.post(
        f"{_GDC_BASE}/files",
        json={
            "filters":    file_filters,
            "fields":     "file_id,file_name,cases.project.project_id,cases.case_id,cases.samples.sample_type,file_size,data_format",
            "format":     "json",
            "size":       max_cases,
        },
        headers={"Content-Type": "application/json"},
    )
    files_resp.raise_for_status()
    files_data = files_resp.json()
    file_hits  = files_data.get("data", {}).get("hits", [])

    # ── Step 2: Get available TCGA projects ───────────────────────────────────
    projects_resp = await client.post(
        f"{_GDC_BASE}/projects",
        json={
            "filters": {
                "op": "=",
                "content": {"field": "program.name", "value": "TCGA"}
            },
            "fields":  "project_id,name,primary_site,summary.case_count",
            "size":    40,
        },
        headers={"Content-Type": "application/json"},
    )
    projects_resp.raise_for_status()
    projects_data = projects_resp.json()
    all_projects  = projects_data.get("data", {}).get("hits", [])

    available_projects = [
        {
            "project_id":    p.get("project_id", ""),
            "name":          p.get("name", ""),
            "primary_site":  p.get("primary_site", ""),
            "case_count":    p.get("summary", {}).get("case_count", 0),
        }
        for p in all_projects[:20]
    ]

    # ── Step 3: Parse file metadata ───────────────────────────────────────────
    expression_files: list[dict[str, Any]] = []
    for hit in file_hits[:max_cases]:
        cases = hit.get("cases", [{}])
        case  = cases[0] if cases else {}
        samples = case.get("samples", [{}])
        sample  = samples[0] if samples else {}

        expression_files.append({
            "file_id":       hit.get("file_id", ""),
            "file_name":     hit.get("file_name", ""),
            "case_id":       case.get("case_id", ""),
            "project":       case.get("project", {}).get("project_id", ""),
            "sample_type":   sample.get("sample_type", ""),
            "file_size_mb":  round(hit.get("file_size", 0) / 1_000_000, 2),
            "data_format":   hit.get("data_format", ""),
            "download_url":  f"https://api.gdc.cancer.gov/data/{hit.get('file_id', '')}",
            "gdc_url":       f"https://portal.gdc.cancer.gov/files/{hit.get('file_id', '')}",
        })

    # ── Step 4: Gene-level summary via GDC gene endpoint ─────────────────────
    gene_summary: dict[str, Any] = {}
    try:
        gene_resp = await client.get(
            f"{_GDC_BASE}/genes",
            params={
                "q":      gene_symbol,
                "fields": "gene_id,symbol,name,biotype,cytoband,description",
                "size":   1,
            },
        )
        gene_resp.raise_for_status()
        gene_hits = gene_resp.json().get("data", {}).get("hits", [])
        if gene_hits:
            g = gene_hits[0]
            gene_summary = {
                "ensembl_id": g.get("gene_id", ""),
                "name":       g.get("name", ""),
                "biotype":    g.get("biotype", ""),
                "cytoband":   g.get("cytoband", ""),
            }
    except Exception as exc:
        logger.debug(f"[TCGA] Gene summary fetch failed: {exc}")

    # ── TCGA mutation count for this gene ─────────────────────────────────────
    mutation_count = 0
    try:
        mut_resp = await client.post(
            f"{_GDC_BASE}/ssms",
            json={
                "filters": {
                    "op": "and",
                    "content": [
                        {"op": "=", "content": {"field": "consequence.transcript.gene.symbol", "value": gene_symbol}},
                        {"op": "=", "content": {"field": "cases.project.program.name", "value": "TCGA"}},
                    ]
                },
                "size": 0,
            },
            headers={"Content-Type": "application/json"},
        )
        mut_resp.raise_for_status()
        mutation_count = mut_resp.json().get("data", {}).get("pagination", {}).get("total", 0)
    except Exception as exc:
        logger.debug(f"[TCGA] Mutation count failed: {exc}")

    return {
        "gene":                gene_symbol,
        "cancer_type_filter":  cancer_type or "pan-cancer",
        "gene_annotation":     gene_summary,
        "tcga_mutation_count": mutation_count,
        "total_files_found":   files_data.get("data", {}).get("pagination", {}).get("total", 0),
        "expression_files":    expression_files,
        "available_tcga_projects": available_projects[:15],
        "gdc_gene_url":        (
            f"https://portal.gdc.cancer.gov/genes/"
            f"{gene_summary.get('ensembl_id', '')}?filters=%7B%22op%22%3A%22and%22%7D"
            if gene_summary.get("ensembl_id") else
            f"https://portal.gdc.cancer.gov/exploration?filters={{\"op\":\"and\",\"content\":[{{\"op\":\"=\",\"content\":{{\"field\":\"genes.symbol\",\"value\":\"{gene_symbol}\"}}}}]}}"
        ),
        "download_instructions": (
            "Files can be downloaded individually via the GDC Data Transfer Tool "
            "or through the GDC portal. Each file contains per-gene STAR read counts. "
            "Use the GDC Client: https://gdc.cancer.gov/access-data/gdc-data-transfer-tool"
        ),
        "analysis_tools": [
            "DESeq2 — differential expression analysis",
            "edgeR — count-based differential expression",
            "TCGAbiolinks (R) — direct GDC data access",
            "TIMER2.0 — tumor immune estimation",
            "cBioPortal — integrative cancer genomics",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CellMarker 2.0 — validated cell type markers
# ─────────────────────────────────────────────────────────────────────────────

@cached("cellmarker")
@rate_limited("default")
@with_retry(max_attempts=3)
async def search_cellmarker(
    gene_symbol:  str = "",
    tissue:       str = "",
    cell_type:    str = "",
    species:      str = "Human",
    max_results:  int = 20,
) -> dict[str, Any]:
    """
    Search CellMarker 2.0 for validated cell type markers.

    CellMarker 2.0 contains 1,000+ cell types with experimentally
    validated marker genes across tissues and species. Essential for:
      - scRNA-seq cell type annotation
      - Cell type deconvolution from bulk RNA-seq
      - Identifying cell-type-specific drug targets

    Args:
        gene_symbol: Gene to find which cell types it marks. Optional.
        tissue:      Tissue to search (e.g. 'lung', 'blood', 'brain').
        cell_type:   Specific cell type (e.g. 'T cell', 'macrophage').
        species:     'Human' | 'Mouse'. Default 'Human'.
        max_results: Results to return (1–100). Default 20.

    Returns:
        {
          query, total_found,
          markers: [{
            cell_name, tissue_type, cancer_type,
            cell_marker_list, marker_source, pmid,
            marker_count
          }],
          gene_expressed_in: [...cell types where gene is a marker...]
        }
    """
    if not any([gene_symbol, tissue, cell_type]):
        raise ValueError("Provide at least one of: gene_symbol, tissue, or cell_type.")

    max_results = BioValidator.clamp_int(max_results, 1, 100, "max_results")
    client      = await get_http_client()

    # CellMarker 2.0 API
    params: dict[str, Any] = {
        "species": species,
        "tissue":  tissue or "",
    }
    if cell_type:
        params["cell_name"] = cell_type
    if gene_symbol:
        params["markers"]   = gene_symbol

    try:
        resp = await client.get(
            "http://xteam.xbio.top/CellMarker/download/all_cell_markers.txt",
            timeout=20.0,
        )
        if resp.status_code != 200:
            raise ValueError("CellMarker download unavailable")

        # Parse TSV format
        lines   = resp.text.strip().split("\n")
        headers = lines[0].split("\t") if lines else []
        results: list[dict[str, Any]] = []

        for line in lines[1:]:
            cols = line.split("\t")
            if len(cols) < len(headers):
                continue

            row = dict(zip(headers, cols))
            row_species = row.get("speciesType", "Human")
            row_tissue  = row.get("tissueType", "").lower()
            row_cell    = row.get("cellName", "").lower()
            row_markers = row.get("cellMarker", "")

            # Filter by species
            if species.lower() not in row_species.lower():
                continue

            # Filter by tissue
            if tissue and tissue.lower() not in row_tissue:
                continue

            # Filter by cell type
            if cell_type and cell_type.lower() not in row_cell:
                continue

            # Filter by gene marker
            if gene_symbol and gene_symbol.upper() not in row_markers.upper():
                continue

            marker_list = [m.strip() for m in row_markers.split(",") if m.strip()]

            results.append({
                "cell_name":          row.get("cellName", ""),
                "tissue_type":        row.get("tissueType", ""),
                "cancer_type":        row.get("cancerType", ""),
                "cell_type":          row.get("cellType", ""),
                "marker_source":      row.get("markerSource", ""),
                "marker_resource":    row.get("markerResource", ""),
                "cell_marker_list":   marker_list,
                "marker_count":       len(marker_list),
                "pmid":               row.get("PMID", ""),
                "pubmed_url":         f"https://pubmed.ncbi.nlm.nih.gov/{row.get('PMID', '')}/" if row.get("PMID") else "",
                "cellmarker_url":     "http://xteam.xbio.top/CellMarker/",
            })

            if len(results) >= max_results:
                break

    except Exception as exc:
        logger.warning(f"[CellMarker] Download failed: {exc}. Using simplified response.")
        # Graceful degradation with direct URL
        return {
            "query":        {"gene_symbol": gene_symbol, "tissue": tissue, "cell_type": cell_type},
            "total_found":  0,
            "markers":      [],
            "error":        (
                "CellMarker direct download failed. "
                "Access the full database at http://xteam.xbio.top/CellMarker/"
            ),
            "direct_url":   "http://xteam.xbio.top/CellMarker/",
            "alternative":  (
                "For programmatic access, download the full marker table from "
                "http://xteam.xbio.top/CellMarker/download/all_cell_markers.txt"
            ),
        }

    # Gene expressed in which cell types?
    gene_expressed_in = list({r["cell_name"] for r in results if gene_symbol})[:20]

    return {
        "query": {
            "gene_symbol": gene_symbol,
            "tissue":      tissue,
            "cell_type":   cell_type,
            "species":     species,
        },
        "total_found":       len(results),
        "markers":           results[:max_results],
        "gene_expressed_in": gene_expressed_in,
        "summary": (
            f"{gene_symbol} is a marker for: {', '.join(gene_expressed_in[:5])}"
            if gene_expressed_in else
            f"Found {len(results)} cell type entries for {tissue or cell_type}"
        ),
        "use_cases": [
            "scRNA-seq cluster annotation",
            "Cell type deconvolution (CIBERSORT, CIBERSORTx)",
            "Flow cytometry panel design",
            "Cell-type-specific drug targeting",
        ],
        "cellmarker_url":   "http://xteam.xbio.top/CellMarker/",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENCODE — regulatory elements (promoters, enhancers, TF binding)
# ─────────────────────────────────────────────────────────────────────────────

@cached("encode")
@rate_limited("default")
@with_retry(max_attempts=3)
async def get_encode_regulatory(
    gene_symbol:     str,
    element_type:    str = "all",
    biosample:       str = "",
    max_results:     int = 15,
) -> dict[str, Any]:
    """
    Search ENCODE for regulatory elements associated with a gene.

    ENCODE (Encyclopedia of DNA Elements) provides ChIP-seq, ATAC-seq,
    and RNA-seq datasets defining the regulatory landscape of human genes:
    promoters, enhancers, CTCF binding sites, TF binding, open chromatin.

    Args:
        gene_symbol:  HGNC gene symbol (e.g. 'TP53', 'MYC').
        element_type: 'promoter' | 'enhancer' | 'CTCF' | 'TF_binding'
                      | 'open_chromatin' | 'all'. Default 'all'.
        biosample:    Cell type/tissue filter (e.g. 'HepG2', 'K562', 'lung').
        max_results:  Results to return (1–50). Default 15.

    Returns:
        {
          gene, element_type,
          regulatory_elements: [{
            accession, title, assay, biosample, target,
            file_count, genome_assembly, encode_url
          }],
          assay_summary, key_datasets
        }
    """
    gene_symbol = BioValidator.validate_gene_symbol(gene_symbol)
    max_results = BioValidator.clamp_int(max_results, 1, 50, "max_results")
    client      = await get_http_client()

    # ENCODE search params
    params: dict[str, Any] = {
        "searchTerm":           gene_symbol,
        "type":                 "Experiment",
        "status":               "released",
        "replicates.library.biosample.donor.organism.scientific_name": "Homo sapiens",
        "format":               "json",
        "limit":                max_results,
        "frame":                "object",
    }

    # Map element type to ENCODE assay
    assay_map = {
        "promoter":       "CAGE",
        "enhancer":       "ChIP-seq",
        "CTCF":           "ChIP-seq",
        "TF_binding":     "ChIP-seq",
        "open_chromatin": "ATAC-seq",
    }
    if element_type != "all" and element_type in assay_map:
        params["assay_term_name"] = assay_map[element_type]

    if biosample:
        params["biosample_ontology.term_name"] = biosample

    resp = await client.get(
        f"{_ENCODE_BASE}/search/",
        params=params,
        headers={
            "Accept": "application/json",
            "User-Agent": "BioMCP/2.0",
        },
    )
    if resp.status_code != 200:
        return {
            "gene":  gene_symbol,
            "error": f"ENCODE returned status {resp.status_code}",
            "regulatory_elements": [],
            "encode_search_url": (
                f"https://www.encodeproject.org/search/?searchTerm={gene_symbol}"
                f"&type=Experiment&status=released"
            ),
        }

    data     = resp.json()
    graph    = data.get("@graph", [])

    elements: list[dict[str, Any]] = []
    assay_counts: dict[str, int]   = {}

    for exp in graph[:max_results]:
        assay  = exp.get("assay_term_name", "")
        target = ""
        targets = exp.get("target", {})
        if isinstance(targets, dict):
            target = targets.get("label", "")
        elif isinstance(targets, list) and targets:
            target = targets[0].get("label", "") if isinstance(targets[0], dict) else str(targets[0])

        biosample_name = ""
        bs = exp.get("biosample_summary", "")
        if bs:
            biosample_name = bs
        else:
            bs_ont = exp.get("biosample_ontology", {})
            if isinstance(bs_ont, dict):
                biosample_name = bs_ont.get("term_name", "")

        accession = exp.get("accession", "")
        assay_counts[assay] = assay_counts.get(assay, 0) + 1

        elements.append({
            "accession":       accession,
            "title":           exp.get("title", "")[:80],
            "assay":           assay,
            "target":          target,
            "biosample":       biosample_name,
            "date_released":   exp.get("date_released", ""),
            "genome_assembly": exp.get("assembly", ["GRCh38"])[0] if exp.get("assembly") else "GRCh38",
            "file_count":      exp.get("files", []) if isinstance(exp.get("files"), int) else len(exp.get("files", [])),
            "encode_url":      f"https://www.encodeproject.org/experiments/{accession}/",
            "data_type":       _classify_encode_element(assay, target),
        })

    return {
        "gene":                  gene_symbol,
        "element_type_filter":   element_type,
        "biosample_filter":      biosample,
        "total_experiments":     data.get("total", len(elements)),
        "regulatory_elements":   elements,
        "assay_summary":         assay_counts,
        "key_regulatory_insights": [
            f"{cnt} {assay} datasets available for {gene_symbol}"
            for assay, cnt in sorted(assay_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ],
        "encode_gene_url": (
            f"https://www.encodeproject.org/search/?searchTerm={gene_symbol}"
            f"&type=Experiment&status=released"
        ),
        "analysis_note": (
            "Download ENCODE files via the ENCODE portal or using the "
            "ENCODE API. BAM and bigWig files are available for visualization "
            "in IGV or UCSC Genome Browser."
        ),
    }


def _classify_encode_element(assay: str, target: str) -> str:
    """Classify ENCODE experiment into regulatory element type."""
    assay_lower  = assay.lower()
    target_lower = (target or "").lower()

    if "atac" in assay_lower:               return "Open chromatin (ATAC-seq)"
    if "cage" in assay_lower:               return "Active promoter (CAGE)"
    if "chip" in assay_lower:
        if "h3k27ac" in target_lower:       return "Active enhancer (H3K27ac)"
        if "h3k4me3" in target_lower:       return "Active promoter (H3K4me3)"
        if "h3k4me1" in target_lower:       return "Poised enhancer (H3K4me1)"
        if "ctcf"    in target_lower:       return "CTCF binding / TAD boundary"
        if "h3k27me3" in target_lower:      return "Polycomb repression (H3K27me3)"
        if target:                           return f"TF binding: {target}"
        return "ChIP-seq"
    if "rna" in assay_lower:               return "RNA expression"
    if "dnase" in assay_lower:             return "Open chromatin (DNase-seq)"
    return assay


# ─────────────────────────────────────────────────────────────────────────────
# MetaboLights — metabolomics datasets
# ─────────────────────────────────────────────────────────────────────────────

@cached("metabolights")
@rate_limited("default")
@with_retry(max_attempts=3)
async def search_metabolomics(
    gene_symbol:    str = "",
    metabolite:     str = "",
    disease:        str = "",
    max_results:    int = 10,
) -> dict[str, Any]:
    """
    Search MetaboLights for metabolomics datasets connecting metabolites
    to genes and diseases.

    MetaboLights is the EBI's reference repository for metabolomics studies.
    Metabolomics complements genomics by measuring the downstream functional
    output of gene activity — connecting genotype to phenotype via metabolism.

    Args:
        gene_symbol: Gene to find related metabolic pathways/studies.
        metabolite:  Metabolite name (e.g. 'glucose', 'lactate', 'ATP').
        disease:     Disease context (e.g. 'cancer', 'diabetes').
        max_results: Studies to return (1–50). Default 10.

    Returns:
        {
          query, total_found,
          studies: [{
            study_id, title, description, organism,
            technology, metabolites_count, factors,
            submission_date, metabolights_url
          }],
          hmdb_compounds: [...],
          kegg_pathways: [...]
        }
    """
    if not any([gene_symbol, metabolite, disease]):
        raise ValueError("Provide at least one of: gene_symbol, metabolite, or disease.")

    max_results = BioValidator.clamp_int(max_results, 1, 50, "max_results")
    client      = await get_http_client()

    # Build search query
    query = " ".join(filter(None, [gene_symbol, metabolite, disease]))

    resp = await client.get(
        f"{_METABOLIGHTS}/study/list",
        headers={"Accept": "application/json"},
    )

    studies: list[dict[str, Any]] = []

    if resp.status_code == 200:
        study_list = resp.json().get("content", [])

        # Filter studies by keyword match in title/description
        for study_id in study_list[:200]:   # scan first 200
            if len(studies) >= max_results:
                break
            try:
                detail_resp = await client.get(
                    f"{_METABOLIGHTS}/study/{study_id}/title",
                    headers={"Accept": "application/json"},
                    timeout=5.0,
                )
                if detail_resp.status_code != 200:
                    continue
                title = detail_resp.json().get("content", "")
                if not title:
                    continue

                # Simple keyword match
                if query.lower() and not any(
                    q.lower() in title.lower()
                    for q in query.split() if len(q) > 3
                ):
                    continue

                studies.append({
                    "study_id":            study_id,
                    "title":               title[:120],
                    "metabolights_url":    f"https://www.ebi.ac.uk/metabolights/study/{study_id}",
                    "download_url":        f"https://ftp.ebi.ac.uk/pub/databases/metabolights/studies/public/{study_id}/",
                })
            except Exception:
                continue

    # Also search HMDB for metabolite connections
    hmdb_compounds: list[dict] = []
    if metabolite or gene_symbol:
        try:
            search_term = metabolite or gene_symbol
            hmdb_resp   = await client.get(
                "https://hmdb.ca/metabolites/search",
                params={"query": search_term, "query_type": "metabolite_name"},
                headers={"Accept": "application/json"},
            )
            if hmdb_resp.status_code == 200:
                hmdb_data = hmdb_resp.json()
                for m in (hmdb_data if isinstance(hmdb_data, list) else [])[:5]:
                    hmdb_compounds.append({
                        "name":      m.get("name", ""),
                        "hmdb_id":   m.get("hmdb_id", ""),
                        "formula":   m.get("formula", ""),
                        "hmdb_url":  f"https://hmdb.ca/metabolites/{m.get('hmdb_id','')}",
                    })
        except Exception:
            pass

    return {
        "query": {
            "gene_symbol": gene_symbol,
            "metabolite":  metabolite,
            "disease":     disease,
        },
        "total_found":     len(studies),
        "studies":         studies[:max_results],
        "hmdb_compounds":  hmdb_compounds,
        "metabolights_url":"https://www.ebi.ac.uk/metabolights/",
        "analysis_tools": [
            "MetaboAnalyst (web) — comprehensive metabolomics analysis",
            "XCMS — LC-MS data processing",
            "mzMine — mass spectrometry data analysis",
            "Pathview — KEGG pathway visualization",
            "MetaboAnalystR — R package for programmatic access",
        ],
        "note": (
            "MetaboLights contains raw and processed metabolomics data. "
            "For pathway enrichment, use MetaboAnalyst with HMDB or KEGG compound IDs."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# UCSC Genome Browser — splice variants and isoforms
# ─────────────────────────────────────────────────────────────────────────────

@cached("ucsc")
@rate_limited("default")
@with_retry(max_attempts=3)
async def get_ucsc_splice_variants(
    gene_symbol:    str,
    genome:         str = "hg38",
    include_alt:    bool = True,
) -> dict[str, Any]:
    """
    Retrieve alternative splicing isoforms and UTR annotations from UCSC.

    Alternative splicing creates protein diversity and is frequently
    dysregulated in disease. This tool returns all known isoforms for
    a gene with exon structure, UTR boundaries, and coding sequence info.

    Args:
        gene_symbol: HGNC gene symbol (e.g. 'TP53', 'BRCA1', 'EGFR').
        genome:      Reference genome assembly ('hg38' | 'hg19'). Default 'hg38'.
        include_alt: Include alternative isoforms. Default True.

    Returns:
        {
          gene, genome,
          canonical_isoform: {...},
          isoforms: [{
            transcript_id, transcript_name, isoform_type,
            chromosome, strand, start, end,
            exon_count, cds_start, cds_end,
            utr5_length, utr3_length, total_length,
            ucsc_url
          }],
          splicing_summary: { total_isoforms, exon_range, ... },
          disease_relevance: [...]
        }
    """
    gene_symbol = BioValidator.validate_gene_symbol(gene_symbol)
    client      = await get_http_client()

    # UCSC Public REST API — track hub endpoint
    resp = await client.get(
        f"{_UCSC_BASE}/search",
        params={
            "search": gene_symbol,
            "genome": genome,
        },
        headers={"Accept": "application/json"},
    )

    isoforms: list[dict[str, Any]] = []
    canonical: dict[str, Any]      = {}

    if resp.status_code == 200:
        search_data = resp.json()
        # UCSC returns matches — get gene coordinates
        matches = search_data.get("results", [])

        for match in matches[:3]:
            # Fetch transcript info for this gene
            chrom = match.get("chrom", "")
            start = match.get("chromStart", 0)
            end   = match.get("chromEnd",   0)

            if chrom and start and end:
                # Get GENCODE transcripts for this region
                tx_resp = await client.get(
                    f"{_UCSC_BASE}/getData/track",
                    params={
                        "genome":  genome,
                        "track":   "knownGene",
                        "chrom":   chrom,
                        "start":   start,
                        "end":     end,
                    },
                    headers={"Accept": "application/json"},
                )
                if tx_resp.status_code == 200:
                    tx_data = tx_resp.json()
                    for tx in tx_data.get("knownGene", [])[:20]:
                        name   = tx.get("name", "")
                        name2  = tx.get("name2", "")

                        # Filter to this gene
                        if gene_symbol.upper() not in name2.upper():
                            continue

                        exon_starts = tx.get("exonStarts", [])
                        exon_ends   = tx.get("exonEnds",   [])
                        exon_count  = len(exon_starts)
                        tx_start    = tx.get("txStart",  start)
                        tx_end      = tx.get("txEnd",    end)
                        cds_start   = tx.get("cdsStart", tx_start)
                        cds_end     = tx.get("cdsEnd",   tx_end)
                        strand      = tx.get("strand",   "+")

                        isoform = {
                            "transcript_id":    name,
                            "gene_name":        name2,
                            "chromosome":       chrom,
                            "strand":           strand,
                            "tx_start":         tx_start,
                            "tx_end":           tx_end,
                            "cds_start":        cds_start,
                            "cds_end":          cds_end,
                            "exon_count":       exon_count,
                            "total_length_bp":  tx_end - tx_start,
                            "cds_length_bp":    cds_end - cds_start,
                            "utr5_length_bp":   abs(cds_start - tx_start),
                            "utr3_length_bp":   abs(tx_end - cds_end),
                            "is_coding":        cds_start < cds_end,
                            "ucsc_url": (
                                f"https://genome.ucsc.edu/cgi-bin/hgGene?hgg_gene={name}"
                                f"&db={genome}"
                            ),
                        }
                        isoforms.append(isoform)

                    break   # found coordinates — stop searching

    # If UCSC direct failed, use NCBI RefSeq as fallback
    if not isoforms:
        try:
            from biomcp.utils import get_http_client as _ghc, ncbi_params
            ncbi_client = await _ghc()
            esearch = await ncbi_client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params=ncbi_params({"db": "gene", "term": f"{gene_symbol}[Gene Name] AND Homo sapiens[Organism]", "retmax": 1}),
            )
            esearch.raise_for_status()
            ids = esearch.json().get("esearchresult", {}).get("idlist", [])
            if ids:
                summ = await ncbi_client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                    params=ncbi_params({"db": "gene", "id": ids[0]}),
                )
                summ.raise_for_status()
                gd = summ.json().get("result", {}).get(ids[0], {})
                genomic = gd.get("genomicinfo", [{}])[0] if gd.get("genomicinfo") else {}
                canonical = {
                    "gene_id":    ids[0],
                    "symbol":     gd.get("name", gene_symbol),
                    "chromosome": gd.get("chromosome", ""),
                    "location":   gd.get("maplocation", ""),
                    "length_kb":  round((genomic.get("chrstop", 0) - genomic.get("chrstart", 0)) / 1000, 1),
                }
        except Exception as exc:
            logger.debug(f"[UCSC] NCBI fallback failed: {exc}")

    # Identify canonical (longest CDS)
    if isoforms:
        canonical_tx = max(isoforms, key=lambda x: x.get("cds_length_bp", 0))
        canonical    = canonical_tx

    # Splicing summary
    exon_counts = [iso.get("exon_count", 0) for iso in isoforms]
    coding      = [iso for iso in isoforms if iso.get("is_coding", False)]

    return {
        "gene":               gene_symbol,
        "genome_assembly":    genome,
        "canonical_isoform":  canonical,
        "total_isoforms":     len(isoforms),
        "isoforms":           isoforms[:20],
        "splicing_summary": {
            "total_isoforms":     len(isoforms),
            "coding_isoforms":    len(coding),
            "noncoding_isoforms": len(isoforms) - len(coding),
            "min_exon_count":     min(exon_counts) if exon_counts else 0,
            "max_exon_count":     max(exon_counts) if exon_counts else 0,
            "median_exon_count":  sorted(exon_counts)[len(exon_counts)//2] if exon_counts else 0,
            "complexity":         (
                "Highly alternatively spliced" if len(isoforms) > 10 else
                "Moderately spliced" if len(isoforms) > 3 else
                "Simple gene structure"
            ),
        },
        "disease_relevance": [
            "Alternative splicing frequently dysregulated in cancer",
            "Isoform-specific expression may affect drug binding",
            "UTR variants can affect mRNA stability and translation",
            "Splice-switching antisense oligonucleotides are therapeutic strategy",
        ],
        "ucsc_gene_url": (
            f"https://genome.ucsc.edu/cgi-bin/hgGene?hgg_gene={gene_symbol}"
            f"&db={genome}"
        ),
        "analysis_tools": [
            "rMATS — differential splicing from RNA-seq",
            "STAR — splice-aware alignment",
            "LeafCutter — splicing QTL analysis",
            "SpliceAI — deep learning splice prediction",
            "VAST-Tools — splicing event quantification",
        ],
    }
