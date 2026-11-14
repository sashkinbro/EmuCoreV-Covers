# EmuCoreV Covers

Original IGDB artwork, proportional portrait covers and transparent 3D PS Vita case derivatives. Artwork is game-level; a serial's region does not establish regional artwork provenance. See `ATTRIBUTION.json`, `identity-manifest.json` and `coverage.json`.

The asset corpus contains 2,326 own-ID artwork entities: all 2,293 covered records in the current IGDB platform-46 snapshot, plus 33 historical bundled records. This includes separately typed legacy, DLC, bundle, homebrew, announced and disputed platform records; an IGDB Vita tag is not a claim that each entity shipped as a native commercial game. All 104 current additions and 33 historical records have explicit retention/release-evidence dispositions in `data/provider-corpus-review.json`. The 48 current provider entities without cover artwork remain explicit in `data/provider-corpus-coverage.json`; no blank cover or different game's artwork is substituted.

The worldwide identity union preserves 82,590 sanitized assertions and 40,786 content IDs from 19 community snapshots, together with dated authoritative IGDB metadata. It contains 4,315 native title IDs across all content types and 3,862 native base title IDs. Of these, 3,434 have selected game-level identities, 3,426 have available artwork, eight have known identity but no provider cover, and 428 have unresolved identity. These 436 identity-or-art gaps remain explicit. PCSE00640 uses a reviewed Shovel Knight base-art default; updates can rename it to Treasure Trove, so its installed edition and regional packaging remain unverified. This is not proof of worldwide historical completeness. Source/region/type/status counts are in `data/worldwide/coverage.json`; current No-Intro bulk, GameTDB, Redump/native-cartridge and delisted/regional source gaps are documented there. The separate release-fact snapshot/review covers the 137 new/historical provider entities and does not override publisher conflicts or infer serials.

Python 3.12+ with `pip install -r requirements.txt` (Pillow and NumPy versions pinned to the verified build):

```
python -m unittest discover -s scripts -v
python scripts/pipeline.py map
python scripts/pipeline.py download --workers 4
python scripts/pipeline.py render --workers 4
python scripts/pipeline.py audit
python scripts/audit_print_fit.py --served
python scripts/font_coverage.py
python scripts/verify_repository.py
python scripts/provider_corpus.py audit
python scripts/privacy_audit.py
```

Committed public identity snapshots reproduce mapping without credentials or the original application database. To refresh public inputs, use `scripts/snapshot_sources.py --database PATH --refresh-vita3k`. The database is opened read-only and immutable. Inspect identity changes before rebuilding.

Private ownership inventories are optional and must stay outside this repository. To inspect one, add `--inventory PATH --local-output OUTSIDE_REPOSITORY` to the snapshot command; only public SFO identity fields are read, never game payloads. For private coverage, run `pipeline.py map --local-inventory OUTSIDE_REPOSITORY --local-report OUTSIDE_REPOSITORY`. Only aggregate counts enter the public manifest, while the ownership list and detailed report stay in the external report. `CATEGORY=gd` identifies a base application and does not prove full-game entitlement; a demo/full conflict is explicitly recorded for PCSE00378.

`index.json` schema 2 maps exact `serials[TITLE_ID]` to string IGDB IDs; `games[IGDB_ID]` contains `path`, `path_3d`, SHA-256, dimensions, original path/hash and IGDB image identity. Paths are relative to this repository. Consumers should use `https://raw.githubusercontent.com/sashkinbro/EmuCoreV-Covers/<reviewed-commit>/` as their base URL and verify the style's hash. Runtime title or fuzzy matching is deliberately absent.

Downloads accept HTTPS only at images.igdb.com, use three bounded attempts, four workers maximum, 32 MiB per image and decoded dimension checks, and resume only after hash verification. The `t_original` endpoint is experimentally verified; IGDB's documented 1080p transformation can upscale smaller originals and is not used as original-quality evidence. Original image format is detected from the bytes because IGDB can return PNG bytes for a `.jpg` source URL.

Flat covers use adaptive transparent 2:3 outer canvases, at least 600×900, and retain the complete original. Every 3D cover uses the same canonical vertical Vita case geometry on an adaptive 2:3 canvas of at least 1200×1800. Only pixel resolution scales. Molded surfaces, perspective and the continuous print wrap derive from EmuCoreA's `psp-case-v13-clean-spine`; title/art/footer composition for unusual artwork follows the actual finished EmuCoreH arcade reference. These are stylized renders, not verified regional packaging or original spine scans.

One printed UV sheet is split continuously across spine, bevel and front.2,188 normal portraits wrap their source artwork directly.40 specified portraits use A-style proportional cropping at independently reviewed title/face-safe anchors, bound to the original image hash/dimensions in `scripts/assets/portrait-layout-overrides.json`. Crops may trim hair/limb/background/credit margins; they are not claims that every source pixel remains in 3D. The original bytes and flat style remain complete.93 square/wide sources use whole artwork with sourced-title and neutral platform graphic panels; five title/subject-sensitive portraits use complete-art poster layouts. No invented game features, ratings, regional PSN claims, OnlyOn labels or edition badges are added. Existing marks embedded in source art are retained.

Source panels are proportionally resampled, with integer raster rounding. Normal artwork itself wraps the visible spine; it is never replaced by a blue side column. Designed outlier regions have purposeful title/platform graphics rather than blank black filler, reflected art or stretched edge pixels. Genuine source black/transparency is preserved within the selected source framing and is never automatically trimmed by color. Small originals keep their honest resolution classification; enlargement creates no new detail. Perspective naturally resamples the printed face. Original downloaded bytes remain unchanged, including one animated GIF; its static derivatives explicitly select frame zero. WebP quality is 98. Dimensions, source crop rectangles, panel bounds, recipe/mark/palette/framing hashes and source identities are recorded. Runtime assets must stay within 32 MiB, 16,384 pixels per dimension and 64×1024×1024 decoded pixels. Software 720×1080 sampling is distinguished from an Android device decoder test.

Retail blue is sampled from Sony's official Tearaway Vita packshot: body median RGB 38/88/160, with separate side/bevel/highlight/header samples. `scripts/assets/vita-plastic-palette.json` records primary source URL, hash and rectangles. Lighting, JPEG and color management prevent a universal physical-plastic RGB claim. The compact authentic left PS glyph/PS VITA wordmark and right PlayStation Network globe/lettering use original source pixels, with provenance in `ATTRIBUTION.json`; no marketing caption or invented globe is typed.

For reproducible quality review, run `python scripts/preview_cases.py --output OUTSIDE_REPOSITORY`; its default samples cover 600×800, 100×100, 640×360 and 3376×4501 source aspects, with source/output hashes, dimensions and a contact sheet.

`data/worldwide/review-dispositions.json` records all 25 original, 35 additional and two supplementary identity dispositions. Plus signs and edition qualifiers are significant. Some same-title provider duplicates and Shovel Knight's version-dependent Treasure Trove rename fail closed; a title ID is not used to guess an edition or entitlement. Store bundles/add-ons sharing a base title ID remain separate source content-ID assertions. Thirteen DLC source title-ID/content-ID contradictions are retained explicitly in `data/worldwide/source-anomalies.json` without an inferred parent join. Artwork is game-level and does not certify region-specific packaging.

`manifest.json` retains download status and source metadata, `derivatives.json` records renderer/source hashes and art rectangles, `3d-manifest.json` is the standalone 3D manifest, `identity-manifest.json` records release evidence and unresolved identities, and `coverage.json` is generated only by decoding and hashing every retained original and generated cover.

`quality-probes.json` compares actual dimensions from original bytes against documented 1080p transformations. `reproducibility.json` records the precise Python, Pillow, NumPy and WebP encoder versions. `verification.json` records structural validation and deterministic regeneration samples in addition to the full decode/hash audit.

`fit-audit.json` compares every selected original source rectangle with its actual printed RGBA panel, verifies continuous spine/bevel/front reconstruction and the same canonical vertical case, checks reviewed crop bindings/nonblank design regions, and checks transparent flat exterior pixels against served derivatives. `font-coverage.json` records actual layout branches and all generated-title glyph/fit checks. `scripts/audit_print_fit.py --sheets OUTSIDE_REPOSITORY` produces paged contact sheets for the entire corpus; `--outliers-only` selects unusual aspect ratios for closer visual review.
