-- GENERATED FILE - do not edit. Edit catalog/collections/*.yaml and run
-- `make catalog-gen`. Per-domain filter views over the base arc_records view.

CREATE OR REPLACE VIEW public.arc_records_genomics AS SELECT * FROM public.arc_records WHERE 'genomics' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_imaging AS SELECT * FROM public.arc_records WHERE 'imaging' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_metabolomics AS SELECT * FROM public.arc_records WHERE 'metabolomics' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_microbiome AS SELECT * FROM public.arc_records WHERE 'microbiome' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_phenotyping AS SELECT * FROM public.arc_records WHERE 'phenotyping' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_proteomics AS SELECT * FROM public.arc_records WHERE 'proteomics' = ANY(omics_domains);
CREATE OR REPLACE VIEW public.arc_records_transcriptomics AS SELECT * FROM public.arc_records WHERE 'transcriptomics' = ANY(omics_domains);
