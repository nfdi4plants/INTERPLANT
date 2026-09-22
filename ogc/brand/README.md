# Brand assets

`src/` holds byte-identical copies of the upstream DataPLANT logos from
https://github.com/nfdi4plants/Branding (MIT license). Do not edit them.

`../static/img/*.svg` is GENERATED from `src/` by
`scripts/generate_brand_assets.py`. Run `make brand-assets` after changing a
source file, and commit both the source and the regenerated output.

The upstream files are not usable as shipped: they declare
`width="100%" height="100%"` with no intrinsic size, and carry an external
DTD reference. The generator sets width/height from the viewBox, strips the
doctype and editor metadata, and injects a `<title>` for screen readers.

## License

The logo files are (c) DataPLANT contributors, MIT licensed. The MIT notice
from the Branding repository applies to everything under `src/` and to the
generated derivatives in `../static/img/`.