# Heuris-BioMCP Agent Guidance

## What this server is for

Heuris-BioMCP exposes a curated bioinformatics MCP surface for literature review, gene and protein lookup, pathway analysis, translational research, CRISPR planning, variant interpretation, and biomedical strategy workflows.

The public tool list is intentionally curated. Prefer the higher-level workflow tools when they match the task instead of stitching together many low-level calls.

## Recommended workflows

### Literature and mechanism grounding

Start with:

- `search_pubmed` for the evidence base
- `get_gene_info` for canonical gene context
- `get_protein_info` or `find_protein` for protein-level detail
- `pathway_analysis` for pathway and mechanism context

### Translational gene review

Use:

- `multi_omics_gene_report` for a broad cross-database synthesis
- `search_cbio_mutations` for cancer mutation context
- `search_gwas_catalog` for trait associations
- `get_gene_disease_associations` for disease links

### Protein structure work

Use:

- `find_protein` to resolve a protein or accession
- `get_alphafold_structure` for public structure models
- `predict_structure_boltz2` only when NVIDIA credentials are configured
- `protein_binding_pocket` or `structural_similarity` for follow-on structure analysis

### CRISPR design and review

Use:

- `crispr_analysis` with `action="design"` for guide design
- `crispr_analysis` with `action="off_target"` for off-target review
- `crispr_analysis` with `action="repair"` for repair template workflows

### Variant interpretation

Use:

- `variant_analysis` with `action="full_report"` for a full interpretation pass
- `variant_analysis` with `action="clinvar"` or `action="population_frequency"` for narrow follow-ups
- `rare_disease_diagnosis` when the entry point is phenotype-first rather than variant-first

### Drug and biomarker work

Use:

- `get_drug_targets` and `find_repurposing_candidates` for target and repurposing ideas
- `drug_interaction_checker` for interaction checks
- `drug_safety` for safety and labeling workflows
- `biomarker_panel_design` and `pharmacogenomics_report` for translational planning

### Research session support

Use `session` when the conversation spans multiple related steps:

- `action="resolve_entity"` to normalize genes, proteins, and diseases
- `action="knowledge_graph"` to inspect the current research graph
- `action="connections"` to look for cross-entity links
- `action="export"` to export provenance
- `action="plan"` to trigger the adaptive planner

## Resource URIs

The server exposes static MCP resources that are useful for agents:

- `biomcp://server/capabilities`
- `biomcp://tools/catalog`

Read these when you need capability status, tool inventory, required arguments, or example payloads.

## Credential-gated capabilities

- `NCBI_API_KEY` is optional. NCBI tools still work without it, but at lower rate limits.
- `NVIDIA_BOLTZ2_API_KEY` or `NVIDIA_NIM_API_KEY` is required for `predict_structure_boltz2`.
- `NVIDIA_EVO2_API_KEY` or `NVIDIA_NIM_API_KEY` is required for `generate_dna_evo2`.
- `BIOGRID_API_KEY` is optional but improves interaction-query throughput where supported.

If a gated tool is unavailable, fall back to the closest non-gated workflow instead of repeatedly retrying the same call.

## Usage notes

- Prefer one high-signal call over a long sequence of overlapping calls.
- `multi_omics_gene_report` is intentionally broad; avoid calling it inside loops for long gene lists.
- Validate identifiers before making claims. For example, use a UniProt accession for protein-specific tasks and HGNC symbols for gene tasks.
- The dispatcher returns structured JSON envelopes. Handle `"status": "error"` responses as expected tool outcomes, not transport failures.

## Example prompts

- "Summarize the evidence for KRAS G12C inhibition in NSCLC and show the main pathways involved."
- "Give me a translational review of TP53 with pathway context and notable disease associations."
- "Design a first-pass CRISPR strategy for PCSK9 and include off-target considerations."
- "Interpret BRCA1 c.68_69delAG and highlight population and ClinVar context."

## Avoid

- Do not assume NVIDIA-powered tools are available on every deployment.
- Do not expose credential values in prompts, examples, or documentation.
- Do not treat low-confidence AI-generated hypotheses as validated findings without supporting evidence.
