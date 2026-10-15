**How do are the our taxonomy metadata reach the portal?**

Via organim ID. The portal's indexer adds taxonomy functions on AWI's side after our harvester runs. All our harvester sends is keywords.organism then AWI's index looks those names up in [Catalogue of Life](https://www.catalogueoflife.org/) and writes the full classification back into the record as keywords.tax_*.

**Details:**

1. Our part: portal/ogc/harvest-repository-dataplant-arcs-ogc.py:53-59 copies the ARC organism names into keywords.organism, e.g. {"name": "Arabidopsis thaliana", "type": "organism"}.
2. AWI's part: after harvesting, the indexer matches each organism name against Catalogue of Life and adds tax_domain, tax_kingdom, tax_phylum, tax_class, tax_order, tax_family, tax_genus and tax_species. It also adds a few ranks the website doesn't show: tax_subkingdom, tax_subfamily, tax_tribe and tax_code. Each entry carries a COL id and a link to its parent, so the hierarchy is complete. I checked the ids against the ChecklistBank API: G26R is Arabidopsis thaliana and CS5HF is Eukaryota. Plant species also get a WorldPlants link (worldplants.de/?deeplink=Arabidopsis-thaliana).
3. The website: the filter panel comes from fixed settings in the page (window.CONFIG.sites.data.config.facets lists keywords.tax_domain.name … keywords.tax_species.name). It's the same Data page for every provider. The filters show up for any record that has tax_* fields.