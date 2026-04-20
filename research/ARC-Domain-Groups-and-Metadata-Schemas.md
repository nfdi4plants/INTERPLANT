# ARC Domain Groups and Metadata Schemas

**Source:** GitLab API survey of `git.nfdi4plants.org` - all 198 public, non-archived projects  
**Script:** `arc_inventory.py`   
**Data files:** `arc_inventory.jsonl` (one ARC per line), `arc_inventory_summary.json`

---

## Table of Contents

- [Methodology](#methodology)
- [Overall Counts](#overall-counts)
  - [ARCs by Primary Domain](#arcs-by-primary-domain)
  - [Most Common Multi-omics Combinations](#most-common-multi-omics-combinations)
- [Domain Groups](#domain-groups)
  - [1. Transcriptomics](#1-transcriptomics-16-single-domain-arcs--many-multi-omics)
  - [2. Proteomics](#2-proteomics-12-single-domain-arcs--many-multi-omics)
  - [3. Metabolomics](#3-metabolomics-5-single-domain-arcs--many-multi-omics)
  - [4. Genomics](#4-genomics-15-single-domain-arcs--multi-omics)
  - [5. Imaging](#5-imaging-12-single-domain-arcs--multi-omics)
  - [6. Phenotyping](#6-phenotyping-15-single-domain-arcs--multi-omics)
  - [7. Microbiome](#7-microbiome-4-single-domain-arcs)
- [Multi-omics ARCs (67 ARCs)](#multi-omics-arcs-67-arcs)
- [Unclassified ARCs (39 ARCs)](#unclassified-arcs-39-arcs)
- [Implications for INTERPLANT](#implications-for-interplant)
  - [WP1 - Schema Mapping](#wp1---schema-mapping)
  - [WP2 - Earth Data Portal Collections](#wp2---earth-data-portal-collections)
- [Data Quality Notes](#data-quality-notes)

---

## Methodology

The idea was to enumerate all public projects on the DataPLANT GitLab instance via the REST API at `https://git.nfdi4plants.org/api/v4`. A project is classified as an ARC if its repository root contains `isa.investigation.xlsx` - the canonical marker per the ARC specification. For each ARC we fetched the folder names under `assays/` and `studies/` and normalised them to canonical domains using a keyword-and-substring mapping (see `arc_inventory.py: DOMAIN_MAP + _SUBSTRING_RULES`).

I added couple of representative metadata fields for each domain as an example for now. The proper structure of the schema to get the complete metadata will be added later.
 
**Note on duplicates:** Several ARCs exist as copies across multiple namespaces (e.g., `Ru_ChlamyHeatstress` appears under `weil/`, `scholz/`, `thomas.naegele/`, and `venn/`). These are separate uploads - not GitLab forks - so the API reports `forked_from_project: null` for all of them. Domain counts include all copies.

---

## Overall Counts

| Metric | Value |
|---|---|
| Public projects surveyed | 198 |
| Projects classified as ARCs | 185 (93%) |
| Non-ARC projects skipped | 13 |

### ARCs by Primary Domain

An ARC with assay folders from exactly one canonical domain is assigned that domain. An ARC with assay folders from two or more canonical domains is Multi-omics. Assay folders that could not be normalised and empty ARCs are counted as Unclassified.

| Domain | ARCs | Notes |
|---|---|---|
| **Multi-omics** | 67 | Two or more domains in a single ARC |
| **Unclassified** | 39 | 16 empty ARCs, ~14 demo/template ARCs, ~9 genuinely novel |
| **Transcriptomics** | 16 | |
| **Genomics** | 15 | |
| **Phenotyping** | 15 | |
| **Imaging** | 12 | |
| **Proteomics** | 12 | |
| **Metabolomics** | 5 | Under-represented; many metabolomics ARCs appear in Multi-omics |
| **Microbiome** | 4 | Eukaryotic metabarcoding, metagenomics, phage |
| **Total** | **185** | |

### Most Common Multi-omics Combinations

| Combination | ARCs |
|---|---|
| Metabolomics + Proteomics | 9 |
| Metabolomics + Transcriptomics | 5 |
| Proteomics + Transcriptomics | 5 |
| Genomics + Phenotyping | 4 |
| Imaging + Phenotyping | 4 |
| Phenotyping + Transcriptomics | 4 |
| Metabolomics + Phenotyping | 4 |
| Genomics + Phenotyping + Transcriptomics | 3 |
| Genomics + Transcriptomics | 3 |
| Metabolomics + Microbiome + Phenotyping + Transcriptomics | 2 |

---

## Domain Groups

### 1. Transcriptomics (16 single-domain ARCs + many Multi-omics)

RNA-seq - bulk, single-cell, and long-read - is the most prevalent omics technology in the registry and the dominant partner in multi-omics ARCs.

**Assay types observed:** RNA-seq (Illumina short-read), IsoSeq / PacBio long-read, Oxford Nanopore RNA-seq, single-cell RNA-seq (scRNA-seq), small RNA-seq, 3D RNA-seq (alternative splicing), differential expression analysis assays.

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `Athaliana_timecourse` | sanja.zenker | `RNA-seq`, `visualizations` |
| `Solanum_lycopersicoides_RNAsequencing` | ceplas / usadellab | `RNA_Extraction`, `RNA_Sequencing` |
| `diffnet-idingo-ddn3` | valanhassan | `Cold_Transcriptomics_Data`, `Heat_Transcriptomics_Data` |
| `Lan_2025_Ppd-H1` | hhu-institute-of-plant-genetics | `FASTQC`, `RNAseq_raw_data`, `Salmon_quantification`, `ThreeDRNAseq` |
| `Talinum fruticosum genome` | hhu-plant-biochemistry | `Brilhaus2015_PE_mRNASeq`, `Maleckova2019_A_Oxford_Nanopore`, `Maleckova2019_C_PacBio_Isoseq` |
| `Barvista_ARC` | usadellab | `a_single_cell_RNA_sequencing`, `a_molecular_cartography` |
| `Carbon Availability Transcriptomics Chlamy` | lux | `Transcriptomics` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | Transcription profiling by RNASeq |
| Study | `ORGANISM` | *Arabidopsis thaliana*, *Solanum lycopersicoides*, *Chlamydomonas reinhardtii*, etc. |
| Study | `FACTOR TYPE` | Treatment (cold, heat, light, CO2), genotype, time point |
| Assay | `TECHNOLOGY TYPE` | nucleic acid sequencing |
| Assay | `MEASUREMENT TYPE` | transcription profiling |
| Assay | `LIBRARY STRATEGY` | RNA-Seq, scRNA-Seq, miRNA-Seq |
| Assay | `LIBRARY SOURCE` | TRANSCRIPTOMIC, TRANSCRIPTOMIC SINGLE CELL |
| Assay | `PLATFORM` | ILLUMINA, OXFORD_NANOPORE, PACBIO_SMRT |
| Assay | `RAW DATA FILE` | FASTQ / BAM |
| Assay | `DERIVED DATA FILE` | count matrices, TPM tables |

---

### 2. Proteomics (12 single-domain ARCs + many Multi-omics)

Mass-spectrometry based proteomics, including DIA/DDA acquisition, label-free quantification (LFQ), TurboID proximity labelling, co-immunoprecipitation (co-IP), and chloroplast sub-proteomics.

**Assay types observed:** LC-MS/MS (data-dependent and data-independent acquisition), TurboID-MS, co-IP + MS, gel-based proteomics (SDS-PAGE + MS), protein stability profiling (deepSTABp), Perseus downstream analysis.

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `TurboIDSampleArc` | zimmer | `TurboIDAssay`, `MS`, `MSEval` |
| `RedoxNetworkTopologyProteomics` | maus | `RedoxNetworkTopologyProteomics` |
| `CurtABC_ChlRe_PPI` | frsommer | `ChlReCurtIP_MS1`, `ChlReCurtIP_MS2`, `PerseusAnalysis` |
| `ColdChloroEnvelope` | trentman | `ChloroplasMembraneEnrichment`, `ChloroplastIsolation`, `ColdChloroEnvelope` |
| `Antifibrotic-effects-of-Oxa` | erkel / venn | `Proteomics` |
| `CPN2060_CoIP` | weil | `competition co-IP assay` |
| `deepSTABp` | nishantk / f_jung | `ComplexTab`, `CrossSpecies`, `ProTstabDatasets` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | protein expression profiling |
| Study | `ORGANISM` | *A. thaliana*, *Synechocystis* sp., fungi |
| Study | `FACTOR TYPE` | treatment, subcellular fraction, genotype |
| Assay | `TECHNOLOGY TYPE` | mass spectrometry |
| Assay | `MEASUREMENT TYPE` | protein expression profiling |
| Assay | `INSTRUMENT NAME` | Orbitrap, Q Exactive, timsTOF |
| Assay | `ACQUISITION MODE` | DDA, DIA |
| Assay | `RAW DATA FILE` | `.raw`, `.mzML` |
| Assay | `DERIVED DATA FILE` | Perseus output, MaxQuant `proteinGroups.txt` |

---

### 3. Metabolomics (5 single-domain ARCs + many Multi-omics)

Untargeted and targeted metabolite profiling by GC-MS and LC-MS. Metabolomics is heavily represented in multi-omics ARCs (9 Metabolomics+Proteomics, 5 Metabolomics+Transcriptomics) but rarely exists as a standalone ARC in this registry.

**Assay types observed:** GC-qTOF untargeted profiling, LC-MS targeted and untargeted, MassHunter-based quantification, GC-MS FAME analysis, LC-MS/MS secondary metabolites (camalexin, flavonoids, betalains).

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `Metabolights338_ARC` | usadellab | `MTBLS338_GCMS_Root_met`, `MTBLS338_negative_Root_met_ms`, `MTBLS338_positive_Root_met_ms` |
| `BrassicaceaePhotosynthesis2023` | ceplas / hhu-plant-biochemistry | `GCMS_Brassicaceae`, `IRGA_Brassicaceae`, `Structure_Brassicaceae` |
| `Annunziata-2025-JXB` | hhu-plant-biochemistry | `lc-ms`, `soluble-sugars-starch`, `sorbitol` |
| `Facultative-CAM-in-Talinum` | scholz | `GCqTOF_targets`, `MassHunter_targets`, `RNASeq` |
| `MARS_ENA-Metabolights` | x.zhou | `ENA_Assay1`, `Metabolights_Assay1` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | metabolite profiling |
| Study | `ORGANISM` | plant species, roots vs. shoots |
| Study | `FACTOR TYPE` | treatment, genotype, tissue |
| Assay | `TECHNOLOGY TYPE` | mass spectrometry |
| Assay | `MEASUREMENT TYPE` | metabolite profiling |
| Assay | `INSTRUMENT NAME` | Agilent GC-qTOF, Waters Xevo |
| Assay | `CHROMATOGRAPHY TYPE` | GC, LC (reverse-phase, HILIC) |
| Assay | `ION MODE` | positive, negative |
| Assay | `RAW DATA FILE` | `.d`, `.mzML`, `.wiff` |
| Assay | `DERIVED DATA FILE` | peak area tables, MetaboAnalyst input |

---

### 4. Genomics (15 single-domain ARCs + multi-omics)

Whole-genome sequencing, genome assembly and annotation, functional genomics (ChIP-seq, DAP-seq, ChAP-seq, ATAC-seq), and population/quantitative genetics (GWAS, BSA-seq).

**Assay types observed:** Illumina WGS, Oxford Nanopore long-read assembly, PacBio HiFi assembly, Hi-C chromosome conformation, ChIP-seq, DAP-seq, ChAP-seq, GWAS, BSA-WGS, amplicon sequencing for genomic verification, genome annotation pipelines.

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `Lupinus_mutabilis_cruickshanks_Genome` | usadellab | `01_DNA_extraction`, `02_sequencing`, `03_Genome_assembly`, `04_Genome_annotation` |
| `Cassava_genome_sequencing_2017` | usadellab | `DNA extraction`, `Genome_annotations`, `Genome_assemblies`, `Sequencing_cassava_paired_reads` |
| `DAP_Seq` | frommer | `01 DNA isolation`, `02 ampDAP-Seq DNA library preparation`, `03 DAP-Seq` |
| `2023_Krueger_prophage_lysis-lysogeny_MrpR` | v.sharma | `ChAPSeq-Illumina` |
| `dormancy_NhuTran_2025` | tntranloc | `GWAS`, `Heat_treatment`, `Maximum_Likelihood_Population_Effects` |
| `camellia_sinensis_genomics` | ceplas | `Sequencing`, `Genome_assemblies`, `Genome_annotations`, `BUSCO_and_Compleasm_db` |
| `10HistoricalPotatoGenomes` | ceplas | `Assembly QC report` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | genome sequencing, chromatin immunoprecipitation, population genetics |
| Study | `ORGANISM` | specific plant or microbe; genome version where known |
| Study | `FACTOR TYPE` | genotype, treatment (ChIP antibody target) |
| Assay | `TECHNOLOGY TYPE` | nucleic acid sequencing |
| Assay | `MEASUREMENT TYPE` | genome sequencing / ChIP-seq / DAP-seq |
| Assay | `LIBRARY STRATEGY` | WGS, ChIP-Seq, DAP-Seq, Hi-C |
| Assay | `PLATFORM` | ILLUMINA, OXFORD_NANOPORE, PACBIO_SMRT |
| Assay | `RAW DATA FILE` | FASTQ |
| Assay | `DERIVED DATA FILE` | assembled FASTA, VCF, BED peak file |

---

### 5. Imaging (12 single-domain ARCs + multi-omics)

A heterogeneous group spanning confocal/CLSM fluorescence microscopy, light-sheet, MRI, drone/UAV imaging, IR thermal imaging, flow cytometry, and backscatter microfluidic imaging. The common thread is spatial or visual data about plant structures, cells, or populations.

**Assay types observed:** CLSM (confocal laser scanning microscopy), spinning-disk confocal, light-sheet microscopy, MRI, IR thermal imaging, UV/white-light imaging, drone aerial imaging, backscatter microfluidic microscopy, flow cytometry, structured illumination microscopy (SIM).

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `map-by-seq_CLSM-stacks` | natural-variation-and-evolution | `CLSM-stacks_DMSO`, `CLSM-stacks_latrunculinB`, `CLSM-stacks_oryzalin` |
| `Zhu2022JXB` | usman.anwer | `IRImaging16C22C`, `IRImagingClockMutants`, `WhiteLightImaging16C22CLD` |
| `Rat MRI + LS` | torsten.stoeter | `LightSheet`, `MRI` |
| `MBEN_Resolve` | michele.bortolomeazzi | `ResolveMolecularCartography` |
| `2026_Synechocystis_single-cell_circadian` | sfb1535_mibinet | `Backscatter_data_analysis_pipeline`, `Microfluidic_single_cell_analysis` |
| `LarvaeDrosophila` | NKandpal | `SpinningDisk` |
| `flyover_redacted` | kMutagene | `drone_image_capture` |
| `bund-et-al_2025` | j.seiffarth | `microscopy` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | microscopy, imaging |
| Study | `ORGANISM` | *A. thaliana*, *Synechocystis*, *Drosophila* |
| Study | `FACTOR TYPE` | drug treatment, genetic background, growth condition |
| Assay | `TECHNOLOGY TYPE` | microscopy / imaging |
| Assay | `MEASUREMENT TYPE` | cell imaging, fluorescence imaging |
| Assay | `INSTRUMENT NAME` | Zeiss LSM 880, Leica SP8, DJI drone model, Bruker MRI |
| Assay | `FLUOROPHORE` | GFP, YFP, mKate, mCherry (confocal-specific) |
| Assay | `IMAGE FORMAT` | TIFF, CZI, LIF, ND2 |
| Assay | `DERIVED DATA FILE` | segmentation masks, quantification tables |

---

### 6. Phenotyping (15 single-domain ARCs + multi-omics)

A broad group covering plant growth measurements, field trial data, plant-pathogen/nematode/microbe interaction assays, and breeding-related trait collection. Includes both controlled-environment and open-field experiments, and spans from single-plant measurements to large multi-year multi-site breeding trials.

**Assay types observed:** Plant growth monitoring (biomass, shoot weight, root length, leaf area), field trial phenotyping (MIAPPE-structured observation units), plant-pathogen interaction assays (infection, confrontation, co-inoculation), historical breeding data (CREA, ICARDA, IHAR station records), nematode assays, photosynthesis measurements (MiniPAM fluorometry, gas exchange).

**Representative ARCs:**

| ARC | Namespace | Description |
|---|---|---|
| `BreedingValue-Public-Dataset` | usadellab | Berry breeding trials (JHI blueberry/raspberry/strawberry field data, 2020–2024) |
| `Curated_wheat_historical_phenotypic_data_from_European_Genebanks` | lange | CREA (Italy) + ICARDA + IHAR (Poland) wheat station records, 1967–2024 |
| `Historical_Phenomics_Wheat_Collection_IPK` | arendd | Spring/winter wheat historical phenomics, IPK Gatersleben |
| `GH25_Sorger_2025` | zarah.sorger | Plant-pathogen interaction (Botrytis, Laibachii, nematode assays) |
| `PGAsEffects` | usadellab | Seed germination, nematode attraction/infection, fungal/bacterial growth assays |
| `Quinoa_Chileanfieldtrial` | ceplas | Photosynthesis (MiniPam), phenology, relative water content |
| `JHI Barley Trial` | feser | MIAPPE observation-unit structured trial data |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | observational study, intervention study, field experiment |
| Study | `ORGANISM` | plant species + cultivar/accession |
| Study | `FACTOR TYPE` | treatment, genotype, location, season, year |
| Study | `GROWTH FACILITY` | greenhouse, growth chamber, field |
| Assay | `TECHNOLOGY TYPE` | phenotyping platform (MIAPPE) |
| Assay | `MEASUREMENT TYPE` | plant growth, yield, pathogen infection rate |
| Assay | `TRAIT NAME` | plant height, shoot fresh weight, leaf area, germination rate |
| Assay | `RAW DATA FILE` | XLSX, CSV (measurement tables) |
| Assay | `UNIT` | cm, g, mm², % (trait-dependent) |

**MIAPPE note:** Several ARCs (JHI trials, Miappe_Showcase_ARC) explicitly structure phenotyping data according to the MIAPPE (Minimum Information About a Plant Phenotyping Experiment) standard with Observation Unit assays. MIAPPE is directly relevant to the Earth Data Portal's collection design.

---

### 7. Microbiome (4 single-domain ARCs)

A small but distinct group covering eukaryotic metabarcoding (18S), metagenomics, and phage genomics. Several multi-omics ARCs also include microbiome assays (e.g., combined 16S/18S + plant transcriptomics in SFB1535 ARCs).

**Assay types observed:** 18S eukaryotic metabarcoding, yam metagenomics, Streptomyces phage isolation.

**Representative ARCs:**

| ARC | Namespace | Assay folders |
|---|---|---|
| `euk_metabarcoding_body_size` | lu.wang.env4all / phytoakmeter | `18S_euk_metabarcoding`, `18S_downstream_analysis`, `18S_raw_processing` |
| `sampleARC_nfcore` | perelo | `YamMetagenome` |
| `Streptomyces-phages` | v.sharma | `Streptomyces-phages_Assay` |

**ISA metadata fields typical for this domain:**

| Level | Field | Notes |
|---|---|---|
| Study | `STUDY DESIGN TYPE` | metagenomics, amplicon sequencing |
| Study | `ORGANISM` | community (not single organism) |
| Study | `FACTOR TYPE` | environment, host species, body compartment |
| Assay | `TECHNOLOGY TYPE` | nucleic acid sequencing |
| Assay | `MEASUREMENT TYPE` | metagenome sequencing |
| Assay | `LIBRARY STRATEGY` | AMPLICON, WGS, WGA |
| Assay | `TARGET GENE` | 18S rRNA, ITS (for metabarcoding assays) |
| Assay | `TARGET SUBFRAGMENT` | V4, V1-V3 |
| Assay | `RAW DATA FILE` | FASTQ |

---

## Multi-omics ARCs (67 ARCs)

Multi-omics ARCs are those with assay folders spanning two or more canonical domains. They are the single largest category and represent the integrative nature of systems biology studies in DataPLANT.

**Most common combinations (67 ARCs total):**

| Combination | Count | Example ARC |
|---|---|---|
| Metabolomics + Proteomics | 9 | `Ru_ChlamyHeatstress` (thomas.naegele) - Growth, Metabolomics, Proteomics, Transcriptomics |
| Metabolomics + Transcriptomics | 5 | `Facultative-CAM-in-Talinum` (scholz) - GCqTOF, MassHunter, RNASeq |
| Proteomics + Transcriptomics | 5 | - |
| Genomics + Phenotyping | 4 | `Buchmann_2025_GP-rapid` - SNP array genotyping + morphological phenotyping |
| Imaging + Phenotyping | 4 | - |
| Phenotyping + Transcriptomics | 4 | `Kaplunova_2025_TPJ` - microbiota + scRNA-seq + plant growth |
| Metabolomics + Phenotyping | 4 | - |
| Genomics + Phenotyping + Transcriptomics | 3 | - |
| Genomics + Transcriptomics | 3 | - |
| Metabolomics + Microbiome + Phenotyping + Transcriptomics | 2 | - |

**Key example - `Ru_ChlamyHeatstress` (thomas.naegele/Ru_ChlamyHeatstress):**
```
assays/
  Growth/            → Phenotyping
  Metabolomics/      → Metabolomics
  Proteomics/        → Proteomics
  Transcriptomics/   → Transcriptomics
```
This ARC integrates four domains in a single plant stress study, demonstrating the canonical DataPLANT multi-omics use case.

---

## Unclassified ARCs (39 ARCs)

The 39 unclassified ARCs break down as:

| Reason | Count |
|---|---|
| Empty (no assay folders yet) | 16 |
| Demo / template ARCs (placeholder assay names: `yourAssayName`, `Assay1`, `measurement1`) | 14 |
| Genuinely novel domain or unrecognised naming | ~9 |

The genuinely unclassified real ARCs include:
- `MGlucoMeter2_6` (sfb1535_mibinet / hhu_molphys_frommer) - glucose biosensor engineering
- `Chem4Onto` (muehlhaus) - DFT quantum chemical simulations
- `LLM_Classifier_Comparison` (tscheid) - AI/ML curation comparison

---

## Implications for INTERPLANT

### WP1 - Schema Mapping

The domain groups above define which ISA metadata fields need to be harvested per collection:

- **Transcriptomics + Genomics:** Focus on `LIBRARY STRATEGY`, `PLATFORM`, `ORGANISM`, raw FASTQ file records. These map cleanly to INSDC/ENA submission schemas.
- **Proteomics + Metabolomics:** `INSTRUMENT NAME`, `CHROMATOGRAPHY TYPE`, `ION MODE`, `ACQUISITION MODE`. These correspond to PRIDE / MetaboLights schemas.
- **Phenotyping:** `TRAIT NAME`, `UNIT`, `GROWTH FACILITY`, `FACTOR TYPE`. Maps to MIAPPE and Breeding API (BrAPI) concepts.
- **Imaging:** `INSTRUMENT NAME`, `FLUOROPHORE`, `IMAGE FORMAT`. No standard schema; closest is BioImage Archive submission format.
- **Microbiome:** `TARGET GENE`, `TARGET SUBFRAGMENT`, `LIBRARY STRATEGY`. Maps to ENA amplicon/metagenomics checklists.

### WP2 - Earth Data Portal Collections

Proposed OGC API Records collection structure based on real ARC counts:

| Collection | ARCs (single-domain + share of Multi-omics) | Priority |
|---|---|---|
| `dataplant-transcriptomics` | 16 + ~30 | High - largest single pool |
| `dataplant-multiomics` | 67 | High - largest category overall |
| `dataplant-genomics` | 15 + ~15 | High |
| `dataplant-proteomics` | 12 + ~25 | High |
| `dataplant-phenotyping` | 15 + ~15 | High - MIAPPE integration |
| `dataplant-imaging` | 12 + ~10 | Medium |
| `dataplant-metabolomics` | 5 + ~25 | Medium - most appear in Multi-omics |
| `dataplant-microbiome` | 4 + ~5 | Low - small pool, growing |

Multi-omics ARCs should appear in all applicable domain collections, not just the aggregate `multiomics` collection, to maximise discoverability.

---

## Data Quality Notes

1. **Assay naming is not standardised.** The same domain appears as `rnaseq`, `RNASeq`, `RNA-seq`, `Transcriptomics`, `Cold_Transcriptomics_Data`, etc. The `arc_inventory.py` normalisation map handles ~380 known variants; 380 unique folder names remain uncovered.

2. **Duplicate ARCs.** `Ru_ChlamyHeatstress` exists as 4 separate uploads with slightly different assay sets. The INTERPLANT harvester should deduplicate on investigation DOI or title before exposing records to the Earth Data Portal.

3. **QC assays mixed with experimental assays.** Many ARCs include Nanodrop, Bioanalyzer, qRT-PCR, and FASTQC folders alongside experimental assays. The `arc_inventory.py` script excludes these from domain counting but they appear in `isa.investigation.xlsx` and need to be handled in the metadata harvester.

4. **Empty and template ARCs.** 30 of 185 ARCs (16%) have no real assay data - they are empty ARC shells or tutorial instances. These should be filtered before populating Earth Data Portal collections, e.g., by requiring at least one non-QC assay folder with associated data files.
