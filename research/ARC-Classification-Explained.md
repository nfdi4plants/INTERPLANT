# How ARCs Were Classified into Domain Groups

**Source data:** GitLab API survey of `git.nfdi4plants.org` - 198 public, non-archived projects, 185 of which are ARCs
**Driving script:** `research/arc_inventory.py`
**Companion document:** `research/ARC-Domain-Groups-and-Metadata-Schemas.md`

---

We did **not** read the contents of `isa.investigation.xlsx` to decide a domain. We classified each ARC purely by looking at the **names of the folders directly under `assays/`**, mapping each name to one canonical domain (Transcriptomics, Proteomics, Metabolomics, Genomics, Imaging, Phenotyping, Microbiome) using a hand-built dictionary of known terms, and then collapsing the ARC's set of domain labels into a single bucket:

- **0 domains** → Unclassified
- **1 domain**  → that domain
- **≥ 2 domains** → Multi-omics

Quality-control folders (Nanodrop, Bioanalyzer, FASTQC, qPCR, DNA/RNA extraction…) are recognised but **do not count** toward the ARC's domain.

---

## The four-step decision process

### Step 1 - Is this project an ARC at all?

For every public, non-archived project on `git.nfdi4plants.org`, we list the files at the root of its default branch.
A project is treated as an ARC **if** that root listing contains the file `isa.investigation.xlsx`. Everything else is dropped.

> Result: 185 of 198 projects classify as ARCs (93%). The 13 non-ARCs are excluded entirely.

### Step 2 - Collect the assay folder names

For each ARC, we list the names of the immediate sub-directories of `assays/` (e.g. `RNA-seq`, `GCMS_Brassicaceae`, `01_DNA_extraction`).
Folder names under `studies/` are recorded for completeness but are **not used** for classification.

### Step 3 - Map each folder name to one canonical label

Each folder name is processed through this pipeline (the function `normalize` in `arc_inventory.py`):

1. Lowercase + trim whitespace.
2. **Hard-coded prefix shortcut** - names starting with `clsm` (e.g. `CLSM-stacks_DMSO`) are labelled `Imaging`.
3. **Exact-name lookup** in a curated dictionary (~50 entries: `rnaseq`, `proteomics`, `metabolomics`, `sequencing`, `microscopy`, `phenotyping`, `nanodrop`, `qpcr`, …).
4. **Substring matching** against an **ordered** list of ~250 keywords. The first match wins, so the order is meaningful:
   - QC keywords are checked first (`fastqc`, `nanodrop`, `bioanalyzer`, `dna extraction`, `rna extraction`) so they are not swallowed by a domain match.
   - Then broad domain stems (`transcriptom`, `proteom`, `metabol`, `microscop`, `phenotyp`, `metagenom`, `microbiota`, …).
   - Then narrower technique terms (`co-ip`, `turboid`, `lcms`, `dap-seq`, `gwas`, `lightsheet`, `mri`, `nematode`, `chlorophyll`, `flow cytometry`, …).
5. **Numeric-prefix retry** - if nothing matched, leading numeric prefixes like `01_`, `G01_`, `1-2_` are stripped and steps 3–4 are run again on the stripped name.
6. If still nothing → `Unclassified`.

Each folder ends up with exactly one label from the set:
`Transcriptomics`, `Proteomics`, `Metabolomics`, `Genomics`, `Imaging`, `Phenotyping`, `Microbiome`, `QC`, or `Unclassified`.

### Step 4 - Collapse folder labels into one ARC-level category

For each ARC:

1. Take the labels of all its assay folders.
2. **Drop QC labels** - quality-control folders don't define a domain.
3. Drop `Unclassified` labels (they don't add a domain either).
4. Take the **set** of what remains (deduplicate).
5. Apply the rule:

   | Number of distinct domains in the set | ARC category |
   |---|---|
   | 0 | **Unclassified** (16 of these had no `assays/` folders at all → "Unclassified (empty)"; the rest had only QC/unrecognised folders) |
   | 1 | **That domain** (e.g. Transcriptomics) |
   | ≥ 2 | **Multi-omics** |

That single rule produces the 8 columns in the headline summary of `ARC-Domain-Groups-and-Metadata-Schemas.md`.

---

## Worked examples

### Example 1 - Single domain, clean naming

ARC: `ceplas/solanum_lycopersicoides_rnasequencing`
Assay folders: `RNA_Extraction`, `RNA_Sequencing`

| Folder | Step | Label |
|---|---|---|
| `RNA_Extraction` | substring `rna extraction` matches the QC list | **QC** (dropped) |
| `RNA_Sequencing` | substring `sequencing` matches → Genomics? **No**: `rna_seq`-style stems are checked earlier. Specifically, lowercase `rna_sequencing` contains `rna_seq` (Transcriptomics) which appears before `sequencing` (Genomics) in the ordered list. | **Transcriptomics** |

Domain set after dropping QC: `{Transcriptomics}` → **Transcriptomics**.

### Example 2 - Single domain, numeric prefix

ARC: `usadellab/Lupinus_mutabilis_cruickshanks_Genome`
Assay folders: `01_DNA_extraction`, `02_sequencing`, `03_Genome_assembly`, `04_Genome_annotation`

| Folder | Result |
|---|---|
| `01_DNA_extraction` | matches `dna_extraction` → **QC** |
| `02_sequencing` | matches `sequencing` → **Genomics** |
| `03_Genome_assembly` | matches `genome assembl` → **Genomics** |
| `04_Genome_annotation` | matches `genome_annot` → **Genomics** |

Domain set: `{Genomics}` → **Genomics**.

### Example 3 - Multi-omics

ARC: `thomas.naegele/Ru_ChlamyHeatstress`
Assay folders: `Growth`, `Metabolomics`, `Proteomics`, `Transcriptomics`

| Folder | Result |
|---|---|
| `Growth` | substring `growth` → **Phenotyping** |
| `Metabolomics` | exact match → **Metabolomics** |
| `Proteomics` | exact match → **Proteomics** |
| `Transcriptomics` | exact match → **Transcriptomics** |

Four distinct domains → **Multi-omics: Metabolomics + Phenotyping + Proteomics + Transcriptomics**.

### Example 4 - QC folders mixed in (stays single-domain)

ARC: `madland/physcomitrium-patens-light-signaling-2022`
Assay folders: `Bioanalyzer`, `Nanodrop`, `RNASeq`

| Folder | Result |
|---|---|
| `Bioanalyzer` | exact match → **QC** (dropped) |
| `Nanodrop` | exact match → **QC** (dropped) |
| `RNASeq` | exact match → **Transcriptomics** |

Domain set: `{Transcriptomics}` → **Transcriptomics**. Without the QC drop step, this would be wrongly labelled as a 3-folder Multi-omics-looking ARC.

### Example 5 - Demo / template ARC ends up Unclassified

ARC: `arc_templates/arc`
Assay folders: `yourAssayName`

| Folder | Result |
|---|---|
| `yourAssayName` | no exact, no substring match, no prefix-strip match | **Unclassified** |

Domain set is empty → **Unclassified**. About 14 ARCs fall here because they are unedited templates (`yourAssayName`, `Assay1`, `measurement1`).

### Example 6 - Empty ARC

ARC: `ceplas/Wanke-2021`
Assay folders: _(none)_

Domain set is empty → **Unclassified (empty)**. 16 ARCs are like this - the ARC scaffold exists but no `assays/<folder>` has been created yet.

---

## Why the order of substring rules matters (a worked edge case)

The folder `RNASeq_raw_data` lowercases to `rnaseq_raw_data`. It contains both `rnaseq` (Transcriptomics) and `sequencing`-like fragments. Because the rules list places transcriptomics stems **before** the generic `sequencing` rule, the result is **Transcriptomics**, which is what we want.

If the order were reversed, every `…sequencing…` folder would silently fall into Genomics - including RNA-seq, ChIP-seq, scRNA-seq, etc. That is why the ordering is intentional and load-bearing.

---

## Resulting headline counts

After steps 1–4 are applied to all 185 ARCs:

| Category | ARCs |
|---|---|
| Multi-omics (any combination of 2+ domains) | 67 |
| Unclassified (39 = 16 empty + 14 demo/template + ~9 genuinely novel) | 39 |
| Transcriptomics | 16 |
| Genomics | 15 |
| Phenotyping | 15 |
| Imaging | 12 |
| Proteomics | 12 |
| Metabolomics | 5 |
| Microbiome | 4 |
| **Total** | **185** |

---

## Known limitations

1. **Folder-name only.** A misnamed assay folder is misclassified, regardless of what `isa.investigation.xlsx` says. We did not read the spreadsheet.
2. **First-match-wins matters.** Adding a new substring rule earlier than an existing one can re-bucket previously-classified ARCs. Any change to the rules list should be re-run end-to-end.
3. **Unclassified is a mixed bag.** Of the 39 Unclassified, only ~9 are genuinely novel domains (e.g. AI/ML curation, DFT chemistry, glucose biosensor engineering). The other 30 are tutorial/template/empty ARCs and should be filtered before populating Earth Data Portal collections.
4. **Duplicates are NOT deduplicated.** ARCs uploaded under multiple namespaces (e.g. `Ru_ChlamyHeatstress` exists under 4 different users) are counted independently - both in the numbers above and in the table below. The `forked_from` field is `null` for all of them because they are separate uploads, not GitLab forks.

---

## Per-ARC classification table

185 rows. Sorted by category, then by ARC name. The "Assay folders" column is truncated when an ARC has more than 4 folders (the count of remaining folders is shown as `(+N more)`).

| ARC (`namespace/path`) | Assay folders (truncated) | Category |
|---|---|---|
| `ceplas/10-historical-potato-genomes` | `Assembly QC report` | **Genomics** |
| `v.sharma/2022_Krueger_pseudokinase_heme_tolerance` | `Illumina_Sequencing` | **Genomics** |
| `v.sharma/2023_Krueger_prophage_lysis-lysogeny_MrpR` | `ChAPSeq-Illumina` | **Genomics** |
| `sfb1535_mibinet/2024_GrowthCoupledHemeBiosensor` | `WholeGenomeSequencing` | **Genomics** |
| `ai.krueger/2024_GrowthCoupledHemeBiosensor` | `WholeGenomeSequencing` | **Genomics** |
| `usadellab/Cassava_genome_sequencing_2017` | `DNA extraction`, `Genome_annotations`, `Genome_assemblies`, `Sequencing_cassava_paired_reads` … (+1 more) | **Genomics** |
| `frommer/DAP_Seq` | `01 DNA isolation`, `02 ampDAP-Seq DNA library preparation`, `03 DAP-Seq` | **Genomics** |
| `tntranloc/dormancy_NhuTran_2025` | `GWAS`, `Generalised_linear_model`, `Heat_treatment`, `Maximum_Likelihood_Population_Effects` … (+2 more) | **Genomics** |
| `arc_templates/Genomics_ARC` | `DNA_extraction`, `Genome_assembly`, `Sequencing` | **Genomics** |
| `ceplas/Kindel-2024` | `Metrics`, `PeakCalling`, `SpeciesSelection` | **Genomics** |
| `melissa.stiebner/Loo_2025_PBJ` | `DNA_extraction for DNA hybridization`, `Genome assembly`, `Hygromycin Test`, `Imaging for DNA hybridization` … (+2 more) | **Genomics** |
| `usadellab/Lupinus_mutabilis_cruickshanks_Genome` | `01_DNA_extraction`, `02_sequencing`, `03_Genome_assembly`, `04_Genome_annotation` | **Genomics** |
| `cdent/PotatoAssemblyARC` | `Assembly QC report` | **Genomics** |
| `ceplas/Schladt_et_al_2024` | `DANS`, `META_PD_Index`, `META_SHR-GFP`, `META_SHR-GFP_All_ROIs` … (+7 more) | **Genomics** |
| `hhu_molphys_frommer/Schladt_et_al_2024` | `DANS`, `META_PD_Index`, `META_SHR-GFP`, `META_SHR-GFP_All_ROIs` … (+7 more) | **Genomics** |
| `sfb1535_mibinet/Synechocystis_circadian_shake_flask_backscatter_microfluidic_phase-contrast` | `Analysis_of_segmentation_data`, `Backscatter_data_analysis_pipeline`, `Microfluidic_single_cell_analysis`, `Shake_flask_cultivation_with_backscatter` | **Imaging** |
| `j.seiffarth/bund-et-al_2025` | `microscopy` | **Imaging** |
| `zimmer/EndocAItosisSampleArc` | `EndocytosisAssay`, `Microscopy`, `PostProcessing` | **Imaging** |
| `kMutagene/flyover_redacted` | `drone_image_capture` | **Imaging** |
| `sfb1535_mibinet/Hasenklever-2024` | `1_neubauer_counting_chamber`, `2_particle_counter`, `3_flow_cytometry` | **Imaging** |
| `NKandpal/LarvaeDrosophila` | `SpinningDisk` | **Imaging** |
| `natural-variation-and-evolution/microscopy_collection/map-by-seq_clsm-stacks` | `CLSM-stacks_DMSO`, `CLSM-stacks_latrunculinB`, `CLSM-stacks_oryzalin`, `YFP-ARK1_running-person-icon` | **Imaging** |
| `kMutagene/Maus_Microbiom` | `Microscopy pictures` | **Imaging** |
| `f.baeumlisberger/Maus_Microbiom` | `Microscopy pictures` | **Imaging** |
| `michele.bortolomeazzi/mben_resolve` | `ResolveMolecularCartography` | **Imaging** |
| `torsten.stoeter/rat-mri-ls` | `LightSheet`, `MRI` | **Imaging** |
| `usman.anwer/Zhu2022JXB` | `ClockGating`, `IRImaging16C22C`, `IRImagingClockMutants`, `WhiteLightImaging16C22CLD` … (+2 more) | **Imaging** |
| `hhu-plant-biochemistry/Annunziata-2025-JXB` | `lc-ms`, `soluble-sugars-starch`, `sorbitol`, `statistical-analyses` | **Metabolomics** |
| `ceplas/BrassicaceaePhotosynthesis2023` | `GCMS_Brassicaceae`, `IRGA_Brassicaceae`, `Structure_Brassicaceae` | **Metabolomics** |
| `hhu-plant-biochemistry/BrassicaceaePhotosynthesis2023` | `GCMS_Brassicaceae`, `IRGA_Brassicaceae`, `Structure_Brassicaceae` | **Metabolomics** |
| `x.zhou/MARS_ENA-Metabolights` | `ENA_Assay1`, `Metabolights_Assay1` | **Metabolomics** |
| `usadellab/metabolights338_arc` | `MTBLS338_GCMS_Root_met`, `MTBLS338_Root_metabolite_profiling_mass_spectrometry_targeted`, `MTBLS338_negative_Root_met_ms`, `MTBLS338_positive_Root_met_ms` | **Metabolomics** |
| `lu.wang.env4all/euk_metabarcoding_body_size` | `18S_downstream_analysis`, `18S_euk_metabarcoding`, `18S_raw_processing` | **Microbiome** |
| `phytoakmeter/euk_metabarcoding_body_size` | `18S_downstream_analysis`, `18S_euk_metabarcoding`, `18S_raw_processing` | **Microbiome** |
| `perelo/samplearc_nfcore` | `YamMetagenome` | **Microbiome** |
| `v.sharma/streptomyces-phages` | `Streptomyces-phages_Assay` | **Microbiome** |
| `felix.zimmermann/2025_mycorrhization_experiment` | `1_experimental_setup`, `2_growth_monitoring`, `3_destructive_sampling` | **Phenotyping** |
| `usadellab/BreedingValue-Public-Dataset` | `2020-jhi-blueberry-mapping-population_20241017`, `2021-jhi-blueberry-mapping-population_20241018`, `2022-jhi-blueberry-bull-mapping-population_20241018`, `2022-jhi-blueberry-mapping-population_20241018` … (+87 more) | **Phenotyping** |
| `lange/Curated_wheat_historical_phenotypic_data_from_European_Genebanks` | `CREA_2005-2006_SAL`, `CREA_2006-2007_SAL`, `CREA_2007-2008_SAL`, `CREA_2008-2009_SAL` … (+96 more) | **Phenotyping** |
| `mary.ngigi/Fe_homeostasis` | `Metalcontent`, `RT-qPCR`, `Rosette and leaf area` | **Phenotyping** |
| `ceplas/Gao-2024` | `AssessmentOfMorphologicalAndGrowth-relatedTraits`, `AssessmentOfPhotosynthesis-relatedParameters`, `StatisticalAnalysis` | **Phenotyping** |
| `mmalisic/Getzke-2023` | `In_vitro_Iron_Mobilization`, `R569_mTn5_screen_for_lack_of_pyoverdine`, `R569_mediated_growth_inhibition_of_RsGMI1600` | **Phenotyping** |
| `zarah.sorger/GH25_Sorger_2025` | `AthalianaInfectionAssay`, `AthalianaShootWeight`, `BiomassStudy`, `BotrytisCinereaAssay` … (+9 more) | **Phenotyping** |
| `arendd/Historical_Phenomics_Wheat_Collection_IPK` | `a_spring_wheat`, `a_weather`, `a_winter_wheat` | **Phenotyping** |
| `feser/jhi-barley-trial` | `with-observation-units`, `without-observation-units` | **Phenotyping** |
| `feser/jhi-test-data` | `with-observation-units`, `without-observation-units` | **Phenotyping** |
| `weil/Miappe_Showcase_ARC` | `PlantHeightMeasurement` | **Phenotyping** |
| `usadellab/PGAsEffects` | `01_ROS_dual_trigger`, `01_ROS_single_trigger`, `01_Seed_germination`, `01_Seedling_development` … (+8 more) | **Phenotyping** |
| `ceplas/quinoa_chileanfieldtrial_c` | `MiniPam`, `Phenology`, `RelativeWaterContent`, `Weather_Data` | **Phenotyping** |
| `shape/shape` | `spring_2020_1`, `spring_2020_2`, `winter_2020_1`, `winter_2020_2` | **Phenotyping** |
| `sfb1535_mibinet/Witting_et_al_Lab_on_chip_2025` | `1_Growth in Multi-Cultivator`, `2_Microfluidic cultivation with homogeneous growth light`, `3_Microfluidic cultivation with gradient growth light`, `4_Microfluidic cultivation with gradient growth light and day night cycle` … (+1 more) | **Phenotyping** |
| `erkel/Antifibrotic-effects-of-Oxa` | `Proteomics` | **Proteomics** |
| `venn/Antifibrotic-effects-of-Oxa` | `Proteomics` | **Proteomics** |
| `training/AthalianaColdStressSugar` | `Proteomics_DataAnalysis`, `Proteomics_MS`, `SugarMeasurement`, `Visualization` | **Proteomics** |
| `trentman/ColdChloroEnvelope` | `ChloroplasMembraneEnrichment`, `ChloroplastIsolation`, `ColdChloroEnvelope` | **Proteomics** |
| `weil/CPN2060_CoIP` | `competition co-IP assay`, `preExperimentAssay` | **Proteomics** |
| `frsommer/CurtABC_ChlRe_PPI` | `ChlReCurtIP_MS1`, `ChlReCurtIP_MS2`, `PerseusAnalysis`, `Syn6803CurT_PD` | **Proteomics** |
| `nishantk/deepstabp` | `ComplexTab`, `CrossSpecies`, `ProTstabDatasets`, `ProtTrans` … (+2 more) | **Proteomics** |
| `f_jung/deepstabp` | `ComplexTab`, `CrossSpecies`, `ProTstabDatasets`, `ProtTrans` … (+2 more) | **Proteomics** |
| `leidel/ProteinSurfaceReactivityPL` | `SASAComputation` | **Proteomics** |
| `maus/redoxnetworktopologyproteomics` | `RedoxNetworkTopologyProteomics` | **Proteomics** |
| `frsommer/TestARCfred` | `Test_MS` | **Proteomics** |
| `zimmer/TurboIDSampleArc` | `MS`, `MSEval`, `TurboIDAssay` | **Proteomics** |
| `sanja.zenker/ath_timecourse` | `RNA-seq`, `visualizations` | **Transcriptomics** |
| `usadellab/Barvista_ARC` | `a_BD_data_analysis`, `a_cell_segmentation`, `a_manual_cell_selection`, `a_molecular_cartography` … (+2 more) | **Transcriptomics** |
| `lux/carbon-availability-transcriptomics-chlamy` | `Transcriptomics` | **Transcriptomics** |
| `hhu-plant-biochemistry/rnaseq-workshop` | `Bernsdorff2016_Illumina`, `Zhu2017_IsoSeq` | **Transcriptomics** |
| `madland/Charabraunii_CentralNodal` | `Fragmentanalyzer`, `Nanodrop`, `rnaseq` | **Transcriptomics** |
| `valanhassan/diffnet-idingo-ddn3` | `Cold_Transcriptomics_Data`, `Heat_Transcriptomics_Data` | **Transcriptomics** |
| `madland/evolutionary-responses-CuZnSODs-inhibition-2023` | `Nanodrop`, `RNASeq_Athaliana_Mpolymorpha`, `RNASeq_Ppatens_Mpolymorpha` | **Transcriptomics** |
| `madland/dicer-like-genes-marchantia-polymorpha-development` | `FragmentAnalyzer`, `Nanodrop_mRNA`, `Nanodrop_sRNA`, `mRNA` … (+1 more) | **Transcriptomics** |
| `hhu-institute-of-plant-genetics/Lan_2025_Ppd-H1` | `FASTQC`, `RNAseq_raw_data`, `Salmon_quantification`, `ThreeDRNAseq` | **Transcriptomics** |
| `hhu-plant-biochemistry/2015_NasserSewelam_DominikBrilhaus` | `rnaseq` | **Transcriptomics** |
| `madland/physcomitrium-patens-light-signaling-2022` | `Bioanalyzer`, `Nanodrop`, `RNASeq` | **Transcriptomics** |
| `martinkuhl/SampleArc_RNASeq` | `Talinum_RNASeq_minimal` | **Transcriptomics** |
| `ceplas/solanum_lycopersicoides_rnasequencing` | `RNA_Extraction`, `RNA_Sequencing` | **Transcriptomics** |
| `usadellab/solanum_lycopersicoides_rnasequencing` | `RNA_Extraction`, `RNA_Sequencing` | **Transcriptomics** |
| `hhu-plant-biochemistry/talinum-fruticosum-genome` | `Brilhaus2015_PE_mRNASeq`, `Brilhaus2015_SE_mRNASeq`, `Maleckova2018_aba_mRNASeq`, `Maleckova2019_A_Oxford_Nanopore` … (+2 more) | **Transcriptomics** |
| `ceplas/VonDahlen-2023` | `AnalysisOfDifferencesInExpression`, `CalculationOfTranscriptAbundance`, `DifferentialExpressionAnalysis`, `GeneExpressionComparison` … (+3 more) | **Transcriptomics** |
| `ceplas/Loo-2024` | `ANOVAForDifferentialEnrichmentOfMetabolites`, `AmpliconSequencingDataAnalysis`, `ConstructionOfGUSReporterLines`, `CorrelationBetweenMicrobesAndMetabolites` … (+6 more) | **Multi-omics: Genomics + Imaging + Metabolomics + Microbiome** |
| `ceplas/Wanke-2023` | `BarleyPhenotyping`, `CRISPRCas9-basedMutagenesis`, `EnzymaticCarbohydrateDigestionAndTLC`, `FungalBarleyColonizationAssays` … (+10 more) | **Multi-omics: Genomics + Imaging + Metabolomics + Phenotyping** |
| `ceplas/betalain_regulation_amaranth` | `BSA_RNAseq`, `BSA_WGS`, `betalain_LCMS_quantification`, `betalain_LCMS_quantification_hairy_roots` … (+4 more) | **Multi-omics: Genomics + Imaging + Metabolomics + Transcriptomics** |
| `t.winkler/betalain_regulation_amaranth` | `BSA_RNAseq`, `BSA_WGS`, `betalain_LCMS_quantification`, `betalain_LCMS_quantification_hairy_roots` … (+4 more) | **Multi-omics: Genomics + Imaging + Metabolomics + Transcriptomics** |
| `ceplas/camellia_sinensis_genomics` | `BUSCO_and_Compleasm_db`, `Genome_annotations`, `Genome_assemblies`, `Mercator_Bins` … (+2 more) | **Multi-omics: Genomics + Metabolomics** |
| `usadellab/camellia_sinensis_genomics` | `BUSCO_and_Compleasm_db`, `Genome_annotations`, `Genome_assemblies`, `Mercator_Bins` … (+1 more) | **Multi-omics: Genomics + Metabolomics** |
| `usadellab/goxr_characterization` | `ChAP-Seq`, `Ethanol_production`, `Ethanol_production_2`, `Transcriptomics` | **Multi-omics: Genomics + Metabolomics + Transcriptomics** |
| `usadellab/ribes_nigrum_genome` | `Metabolite_measurement`, `RNASeq_drought`, `Ribes_nigrum_genome_sequencing`, `qRT-PCR` | **Multi-omics: Genomics + Metabolomics + Transcriptomics** |
| `ceplas/Wippel-2021` | `AbsoluteQuantificationOfBacteria`, `BacterialGenomeAssemblyAndAnnotation`, `CollectionOfRootExudates`, `Culture-independentCommunityProfiling` … (+11 more) | **Multi-omics: Genomics + Microbiome + Transcriptomics** |
| `sfb1535_mibinet/2025_IronAndHemeRegulatoryNetworks` | `1-1_GrowthMonitoring-taggedVariants`, `1-2_qPCR-taggedVariants`, `2-1_Sequencing and Analysis`, `2-2_ChAP-analysis` … (+2 more) | **Multi-omics: Genomics + Phenotyping** |
| `tntranloc/epidom_NhuTran_2026` | `Bayesian_model_quantiative_genetics`, `Machine_learning`, `Offspring`, `Phenotyping` … (+3 more) | **Multi-omics: Genomics + Phenotyping** |
| `ceplas/helmsorig-2024-eam7` | `DNA_extraction`, `MSA_dissection`, `RNA_extraction`, `biparental_mapping` … (+7 more) | **Multi-omics: Genomics + Phenotyping** |
| `hhu-institute-of-plant-genetics/helmsorig-2024-eam7` | `DNA_extraction`, `MSA_dissection`, `RNA_extraction`, `biparental_mapping` … (+7 more) | **Multi-omics: Genomics + Phenotyping** |
| `hhu-institute-of-plant-genetics/Buchmann_2025_GP-rapid` | `G01_Selection_of_five_GPR_lines`, `G02_SNP_array_genotyping`, `G03_RNAseq_genotyping`, `P01_Morphological_comparison_LD_data` … (+3 more) | **Multi-omics: Genomics + Phenotyping + Transcriptomics** |
| `hhu-institute-of-plant-genetics/haraldsson-2026-hordeum_erectifolium_genome` | `G01-ONT`, `G02-10X`, `G03-RNASeq`, `G04-HiC` … (+11 more) | **Multi-omics: Genomics + Phenotyping + Transcriptomics** |
| `hhu-institute-of-plant-genetics/Hordeum-vulgare-ft1-RNAseq` | `00_ft1_mutant_generation`, `01_RNA_extraction`, `02_Illumina_sequencing`, `03_quality_control` … (+13 more) | **Multi-omics: Genomics + Phenotyping + Transcriptomics** |
| `sfb1535_mibinet/2025_CoBiSe` | `CNA`, `Expression_and_Purification`, `In_vitro_characterization_IronSenseR`, `In_vivo_C_glutamicum` … (+5 more) | **Multi-omics: Genomics + Proteomics** |
| `mmiras/RDA2` | `Bombardment`, `Immunoblots`, `Localization`, `Nbenthamiana_transport` … (+2 more) | **Multi-omics: Genomics + Proteomics** |
| `usadellab/2026_geobacillus_thermoleovorans` | `01_Sequencing-Illumina`, `02_Sequencing-ONT`, `03_Sequencing-Illumina-RNA`, `04_read_quality_ONT` … (+7 more) | **Multi-omics: Genomics + Transcriptomics** |
| `madland/spirogyra-pratensis-genome` | `RNA-Seq`, `WGS_longreads`, `WGS_shortreads` | **Multi-omics: Genomics + Transcriptomics** |
| `hhu-plant-biochemistry/triesch2025_moricandia_snrna_seq` | `01_find_homologs`, `02_final_experiment`, `03_a_thaliana_comparison`, `rnaseq` | **Multi-omics: Genomics + Transcriptomics** |
| `ceplas/Moormann-2025` | `AnalysisOfSeedlingRespiration`, `GSTActivityAssay`, `MassSpectrometryAdultPlantPst`, `MassSpectrometrySeedlings` … (+8 more) | **Multi-omics: Imaging + Metabolomics + Phenotyping + Proteomics** |
| `j.moormann/Moormann-2025` | `AnalysisOfSeedlingRespiration`, `GSTActivityAssay`, `MassSpectrometryAdultPlantPst`, `MassSpectrometrySeedlings` … (+8 more) | **Multi-omics: Imaging + Metabolomics + Phenotyping + Proteomics** |
| `sfb1535_mibinet/2025_Expression_System_Adeanei` | `S1_1_rDNA-spacers-on-different-chrosomosomes`, `S2_1_Genomic-map-of-Adea319`, `S2_2_Verification-of-genomic-integration-by-PCR`, `S2_3_Verification-of-T7RNAP-production-by-Western-Blot` … (+18 more) | **Multi-omics: Imaging + Phenotyping** |
| `hhu-microbial-cell-biology/2025_Expression_System_Adeanei` | `S1_1_rDNA-spacers-on-different-chrosomosomes`, `S2_1_Genomic-map-of-Adea319`, `S2_2_Verification-of-genomic-integration-by-PCR`, `S2_3_Verification-of-T7RNAP-production-by-Western-Blot` … (+18 more) | **Multi-omics: Imaging + Phenotyping** |
| `ceplas/Guichard-2024` | `AutophagicActivityAssay`, `ComparisonOfAutophagicActivityInRoots`, `FluoresceinDiffusionAssay`, `PlantGrowthAndImageAnalysisOfSucroseTreatmentAssay` … (+1 more) | **Multi-omics: Imaging + Phenotyping** |
| `usadellab/quinoa_chileanfieldtrial` | `Chlorophyll_Fluorescence`, `Harvest`, `Imaging`, `Morphology` … (+4 more) | **Multi-omics: Imaging + Phenotyping** |
| `sfb1535_mibinet/Muentjes_et_al-2025` | `A1_Western blot analysis LD reporter candidates`, `A2_Protein localization LD reporter candidates`, `A3_Erg6 protein localization with different promotors`, `A4_Erg6-Kat protein localization` … (+2 more) | **Multi-omics: Imaging + Phenotyping + Proteomics** |
| `hhu-institute-for-microbiology/biotechnology/Muentjes_et_al-2025` | `A1_Western blot analysis LD reporter candidates`, `A2_Protein localization LD reporter candidates`, `A3_Erg6 protein localization with different promotors`, `A4_Erg6-Kat protein localization` … (+2 more) | **Multi-omics: Imaging + Phenotyping + Proteomics** |
| `ceplas/Chandrasekar-2022` | `Isolation of extracellular polysaccharide matrix`, `MALDI-TOF analysis of Si EPS and CW`, `Microscopy of S indica EPS matrix and CW`, `Proteome analysis of S indica EPS matrix CW and cullture filtrate` | **Multi-omics: Imaging + Proteomics** |
| `sfb1535_mibinet/Sankaranarayanan-2023` | `S1_A1_microscopy_yeast`, `S1_A2_microscopy_hyphae`, `S2_A1_microscopy_Rrm4-Ada_Rrm4-Gfp`, `S2_A2_protein_expression` … (+20 more) | **Multi-omics: Imaging + Transcriptomics** |
| `sfb1535_mibinet/Kaplunova_2025_TPJ` | `Microbiota Profiling`, `Microbiota turnover`, `Rice ArtSoil shoot length`, `Shoot Fresh Mass` … (+4 more) | **Multi-omics: Metabolomics + Microbiome + Phenotyping + Transcriptomics** |
| `hhu_molphys_frommer/published/Kaplunova_2025_TPJ` | `Microbiota Profiling`, `Microbiota turnover`, `Rice ArtSoil shoot length`, `Shoot Fresh Mass` … (+4 more) | **Multi-omics: Metabolomics + Microbiome + Phenotyping + Transcriptomics** |
| `micwij/cmqtl_val1_arc` | `cmQTL_val1_GH_2020_GC_MS`, `cmQTL_val1_GH_2020_apolar_LC_MS`, `cmQTL_val1_GH_2020_phenotype`, `cmQTL_val1_GH_2020_polar_LC_MS` | **Multi-omics: Metabolomics + Phenotyping** |
| `usadellab/Cold_salt_stress_Capsicum` | `Analysis of flavonoids`, `Analysis of phenolics`, `Biomass`, `Growth and leaf color` … (+2 more) | **Multi-omics: Metabolomics + Phenotyping** |
| `xue.xiao/DPPN_SICO_project` | `Leaf LC-MS metabolic fingerprint`, `Leaf terpenoids`, `Morphology`, `Root terpenoids` … (+1 more) | **Multi-omics: Metabolomics + Phenotyping** |
| `ceplas/Germann-2023` | `AbsorptionSpectraAndODMeasurements`, `DCWMeasurement`, `GC-MSMeasurementsForTheQuantificationOfSqualene`, `MetabolicModeling` … (+3 more) | **Multi-omics: Metabolomics + Phenotyping** |
| `micwij/canal-1-multiomics-analysis` | `canal-1_OX_Phenotyping`, `canal-1_PS_LiCOR`, `canal-1_PS_multispeq`, `canal-1_Phenotyping` … (+7 more) | **Multi-omics: Metabolomics + Phenotyping + Proteomics + Transcriptomics** |
| `thomas.naegele/Ru_ChlamyHeatstress` | `Growth`, `Metabolomics`, `Proteomics`, `Transcriptomics` | **Multi-omics: Metabolomics + Phenotyping + Proteomics + Transcriptomics** |
| `ceplas/DeJager-2024` | `AssessmentOfPlantResistanceToPseudomonasSyringae`, `Co-cultivationWithBurkholderiaGlumae`, `DeterminationOfBacterialTiter`, `MetaboliteAnalysis` … (+3 more) | **Multi-omics: Metabolomics + Phenotyping + Transcriptomics** |
| `zimmer/2024_Kitashova_et_al_subcellular` | `GC-MS Metabolomics`, `LC-MS Proteomics` | **Multi-omics: Metabolomics + Proteomics** |
| `thomas.naegele/2024_Kitashova_et_al_subcellular` | `GCMS NAF`, `GCMS`, `LC-MS Proteomics`, `LCMS` … (+1 more) | **Multi-omics: Metabolomics + Proteomics** |
| `ceplas/Angermann-2025` | `CarbohydrateQuantification`, `CarbonAndNitrogenQuantification`, `ChlorophyllQuantification`, `ElementalAnalysis` … (+7 more) | **Multi-omics: Metabolomics + Proteomics** |
| `ceplas/Angermann-2024` | `AminoAcids`, `Cellulose`, `Chlorophyll`, `ProteinQuantification` … (+6 more) | **Multi-omics: Metabolomics + Proteomics** |
| `c.angermann/BalancingNutrientRemobilizationAndPhotosynthesis-ProteomicInsightsIntoTheDualRoleOfLupinCotyledonsAfterGermination` | `CarbohydrateQuantification`, `CarbonAndNitrogenQuantification`, `ChlorophyllQuantification`, `ElementalAnalysis` … (+7 more) | **Multi-omics: Metabolomics + Proteomics** |
| `arc_templates/Metabolomics_ARC` | `Mass spectrometry`, `Metabolite extraction`, `Metabolomics computational analysis` | **Multi-omics: Metabolomics + Proteomics** |
| `c.angermann/ProteinAndAminoAcidMetabolismDuringLupinGermination` | `AminoAcids`, `Cellulose`, `Chlorophyll`, `ProteinQuantification` … (+6 more) | **Multi-omics: Metabolomics + Proteomics** |
| `ceplas/Wrobel-2023-CastorBeanEndospermProteome` | `2_2-FAME-analysis`, `2_3-OrganellesFromEndosperm`, `2_4-EnzymeActivityOrganellarMarkers`, `2_5-OrganellarMembraneIsolation` … (+4 more) | **Multi-omics: Metabolomics + Proteomics** |
| `hhu-plant-biochemistry/Wrobel-2023-CastorBeanEndospermProteome` | `2_2-FAME-analysis`, `2_3-OrganellesFromEndosperm`, `2_4-EnzymeActivityOrganellarMarkers`, `2_5-OrganellarMembraneIsolation` … (+4 more) | **Multi-omics: Metabolomics + Proteomics** |
| `hhu-plant-biochemistry/Brilhaus-2016-Talinum` | `Brilhaus2015_PE_mRNASeq`, `Brilhaus2015_SE_mRNASeq`, `CMML_15-0001_GCqTOF-Masshunter-Quant`, `CMML_15-0001_GCqTOF` … (+1 more) | **Multi-omics: Metabolomics + Transcriptomics** |
| `scholz/Facultative-CAM-in-Talinum` | `GCqTOF_targets`, `MassHunter_targets`, `RNASeq` | **Multi-omics: Metabolomics + Transcriptomics** |
| `brilator/Facultative-CAM-in-Talinum` | `GCqTOF_targets`, `MassHunter_targets`, `RNASeq` | **Multi-omics: Metabolomics + Transcriptomics** |
| `hhu-plant-biochemistry/Maleckova-2019-Talinum-ABA` | `CMML_18-0008_GC-MS-MasshunterQuant`, `CMML_18-0008_GC-MS`, `CMML_18-0008_HPLC-DAD`, `CMML_18-0008_LCqTOF-MasshunterQuant` … (+4 more) | **Multi-omics: Metabolomics + Transcriptomics** |
| `hhu-plant-biochemistry/Samuilov-2018-BOU-PSP` | `CMML_16-0016_GCMS-MasshunterQuant`, `CMML_16-0016_GCMS`, `CMML_16-0016_HPLC`, `CMML_17-0035_GCMS-MasshunterQuant` … (+5 more) | **Multi-omics: Metabolomics + Transcriptomics** |
| `sfb1535_mibinet/2024_Devan-Sai_et_al_PNAS` | `S1_A1_Protein structure prediction`, `S1_A2_Protein Purification for structural studies`, `S1_A3_Size exclusion chromatography of H-Rrm4-MLLE3`, `S1_A4_Western blot analysis of GST pull-down experiments with MLLE3 versions` … (+30 more) | **Multi-omics: Phenotyping + Proteomics** |
| `venn/LPA2_ComplexomeProfiling_Chlamy` | `Blotting`, `GelBasedProteomics`, `Growth tests`, `phenotypic analysis` … (+1 more) | **Multi-omics: Phenotyping + Proteomics** |
| `ceplas/Chitinase_RE_2024_2` | `Chitinase activity assay`, `Mass spectrometry analysis`, `Phenotypic analysis chitinase protection`, `Phenotypic_analysis_plant_protection_Si` … (+5 more) | **Multi-omics: Phenotyping + Proteomics + Transcriptomics** |
| `ruben.eichfeld/Chitinase_RE_2024_2` | `Chitinase activity assay`, `Mass spectrometry analysis`, `Phenotypic analysis chitinase protection`, `Phenotypic_analysis_plant_protection_Si` … (+5 more) | **Multi-omics: Phenotyping + Proteomics + Transcriptomics** |
| `sfb1535_mibinet/a-08-zoellner-2025` | `Clipping`, `DNS Assay`, `Growth Curves`, `Motility` … (+3 more) | **Multi-omics: Phenotyping + Transcriptomics** |
| `sfb1535_mibinet/MibiNet_Data_Showcases` | `S1_A1_Biolector_run`, `S1_A2_Biolector_run_analysis`, `S2_A1_Microarray` | **Multi-omics: Phenotyping + Transcriptomics** |
| `hhu_molphys_frommer/published/suxManuscript2025` | `Clipping`, `DNS Assay`, `Growth Curves`, `Motility` … (+3 more) | **Multi-omics: Phenotyping + Transcriptomics** |
| `d.psaroudakis/TomatoHeatMultiOmics-Moneymaker` | `ftir-analysis`, `phenotyping`, `rna-sequencing` | **Multi-omics: Phenotyping + Transcriptomics** |
| `ceplas/ARC_SiCHIT2_B` | `Mass spec assay`, `Phylogeny`, `ROS`, `chitinase assay` … (+1 more) | **Multi-omics: Proteomics + Transcriptomics** |
| `ruben.eichfeld/ARC_SiCHIT2_B` | `Mass spec assay`, `Phylogeny`, `ROS`, `chitinase assay` … (+1 more) | **Multi-omics: Proteomics + Transcriptomics** |
| `weil/Ru_ChlamyHeatstress` | `Proteomics`, `Proteomics_Imputation`, `Transcriptomics` | **Multi-omics: Proteomics + Transcriptomics** |
| `scholz/Ru_ChlamyHeatstress` | `Proteomics`, `Transcriptomics` | **Multi-omics: Proteomics + Transcriptomics** |
| `venn/Ru_ChlamyHeatstress` | `Proteomics`, `Proteomics_Imputation`, `Transcriptomics` | **Multi-omics: Proteomics + Transcriptomics** |
| `sfb1535_mibinet/MGlucoMeter2_6` | `Candidate selection of MGlucoMeter Generation 2`, `In vitro analysis of MGlucoMeter2_6 variants`, `In vivo detection of glucose`, `Monitoring uptake of glucose into Arabidopsis roots` | **Unclassified** |
| `arc_templates/arc` | `yourAssayName` | **Unclassified** |
| `weil/ARC-Export-TestFixture` | `SharedSampleWithStudy`, `UnrelatedAssay` | **Unclassified** |
| `x.zhou/sample_arc_model` | `Assay1`, `Assay2` | **Unclassified** |
| `kMutagene/ArcPrototype` | `measurement1`, `measurement2` | **Unclassified** |
| `muehlhaus/ArcPrototype` | `measurement1`, `measurement2` | **Unclassified** |
| `marcel/arc-prototype-test` | `measurement1`, `measurement2` | **Unclassified** |
| `shape/bridge-core50` | `tmp` | **Unclassified** |
| `muehlhaus/Chem4Onto` | `DFTsim` | **Unclassified** |
| `ceplas/cplantbox_simulations` | `Assay1`, `Assay2` | **Unclassified** |
| `usadellab/cplantbox_simulations` | `Assay1`, `Assay2` | **Unclassified** |
| `DiP/DiP-KS/dip-ressourcen` | `yourAssayName` | **Unclassified** |
| `f_jung/HeatshockTubercolosisStressitance` | `YourAssay` | **Unclassified** |
| `zimmer/LFSLargeFilesUploadTest3` | `10gbBatch`, `a1` | **Unclassified** |
| `tscheid/LLM_Classifier_Comparison` | `Data-based Curation`, `LLM-based Curation`, `Visualization` | **Unclassified** |
| `lucas.mueller/Lucas_Mueller_PhD_ARC` | `data` | **Unclassified** |
| `hhu_molphys_frommer/published/MGlucoMeter2_6` | `Candidate selection of MGlucoMeter Generation 2`, `In vitro analysis of MGlucoMeter2_6 variants`, `In vivo detection of glucose`, `Monitoring uptake of glucose into Arabidopsis roots` | **Unclassified** |
| `thomas.naegele/OMICS_DB` | `Code`, `Data`, `Test` | **Unclassified** |
| `martinkuhl/SampleARC_Proteomics` | `assay1` | **Unclassified** |
| `mrspaulinehans/QualIQon_v1.0` | `dilutionSeries_Chlamy`, `workflow` | **Unclassified** |
| `caroott/RatioLFQ` | `DilutionSeries` | **Unclassified** |
| `marcel/test-template` | `yourAssayName` | **Unclassified** |
| `v.srivastav/triticum` | `Assay` | **Unclassified** |
| `stetter-lab/amaranth_seed_color` | _(empty)_ | **Unclassified (empty)** |
| `nrahnama/arabis-contemporary-hybridization` | _(empty)_ | **Unclassified (empty)** |
| `thomas.naegele/Bagshaw_et_al_HXK1_CHUP1` | _(empty)_ | **Unclassified (empty)** |
| `stetter-lab/chromatin_amaranth_2025` | _(empty)_ | **Unclassified (empty)** |
| `t.winkler/chromatin_amaranth_2025` | _(empty)_ | **Unclassified (empty)** |
| `mrspaulinehans/DevContainerAndCWL` | _(empty)_ | **Unclassified (empty)** |
| `ceplas/FokoKuate-2023` | _(empty)_ | **Unclassified (empty)** |
| `plantchromatin/FT_Genome_Biology_2026` | _(empty)_ | **Unclassified (empty)** |
| `ceplas/Getzke-2023` | _(empty)_ | **Unclassified (empty)** |
| `andreaschrader/Grow-an-ARC_Example` | _(empty)_ | **Unclassified (empty)** |
| `hsaker/NewArc` | _(empty)_ | **Unclassified (empty)** |
| `mrspaulinehans/QualIQon_Tool` | _(empty)_ | **Unclassified (empty)** |
| `thomas.naegele/Subcellular_analysis_of_metabolic_network_dynamics_under_elevated_CO2` | _(empty)_ | **Unclassified (empty)** |
| `usadellab/Teosinte` | _(empty)_ | **Unclassified (empty)** |
| `ceplas/triesch2023_brassicaceae_transposons` | _(empty)_ | **Unclassified (empty)** |
| `ceplas/Wanke-2021` | _(empty)_ | **Unclassified (empty)** |
