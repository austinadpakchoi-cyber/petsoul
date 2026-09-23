# Garden layer asset provenance

Generated on 2026-09-22 with the built-in `image_gen` tool. Each asset was generated in one separate call, visually inspected, copied into this directory without pixel editing, and inspected for real alpha. Original generated files remain intact.

Visual reference inspected: `E:/petsoul-audit/petsoul/PetJourneyWeb/output/design/web-v1-keyframes-20260922/home-present.png`. The reference informed the warm cinematic garden lighting and material treatment; it was not used as an edit target.

## Files and verification

All three PNGs are `Format32bppArgb` with true transparency, not a painted white or checkerboard background. Alpha bounds use `alpha > 8`, with inclusive pixel coordinates. Transparent pixels have alpha 0; partial-alpha pixels have alpha between 1 and 254.

| Final file | Dimensions | Bytes | Transparent pixels | Partial-alpha pixels | Alpha bounds (left, top, right, bottom) |
| --- | --- | --- | --- | --- | --- |
| `plot-soil.png` | 1470 × 1070 | 1,348,072 | 952,475 | 620,133 | 67, 278, 1415, 883 |
| `crop-sprouts.png` | 1448 × 1086 | 917,117 | 1,166,567 | 405,547 | 87, 279, 1352, 855 |
| `crop-tomato.png` | 1448 × 1086 | 1,778,219 | 845,233 | 726,520 | 110, 115, 1367, 1006 |

The transparent margins differ. Position plant overlays independently using their effective bounds rather than stretching all layers into the same rectangle. The intended rendered garden-bed size is approximately 110 × 80 CSS pixels.

## Uses and state boundaries

- `plot-soil.png`: one fixed wooden-frame and soil base for every plot stage. Empty and harvested states share this base.
- `crop-sprouts.png`: plant-only overlay for seedlings and growing stages; vary display scale as appropriate. It can provide a generic green plant treatment when a crop-specific mature asset is unavailable, accompanied by the actual crop name.
- `crop-tomato.png`: plant-only overlay for ripe tomato crops. Do not use this art for other crop species.
- These assets are visual layers only. Crop species, growth stage, maturity, harvest availability, inventory, and rewards must come from existing application state.

## plot-soil.png

Original source: `C:/Users/1/.codex/generated_images/01a0c7cf-cdda-7c12-9ccf-d445c50f3c80/exec-72367530-858b-4e88-b2bd-ec932a8884f3.png`

Final file: `E:/petsoul-audit/petsoul/PetJourneyWeb/src/features/home/assets/living/plot-soil.png`

Full prompt:

```text
Use case: stylized-concept. Asset type: one transparent PNG sprite layer for a warm 2.5D pet garden web game. Generate ONE isolated empty raised vegetable bed, no other objects. Camera three-quarter view, mildly looking down about 35 degrees, shallow low-profile rectangular honey-brown wooden plank frame, dark rich loose soil filling the bed, realistic softened wood grain and tiny soil clods. The bed is slightly wider than deep; front edge mostly horizontal, receding side edges gentle perspective, low centre of gravity. Style: refined soft cinematic storybook garden, tactile warm natural materials, warm afternoon sunlight from upper left, soft pale warm highlights, credible small contact shadow beneath the wooden bed. Composed centered as a complete intact object with generous transparent margin; single asset, not a scene or icon. Intended to display at approximately 110x80 CSS pixels so silhouette is crisp, details restrained. Output a genuinely transparent-background RGBA PNG with alpha, not white or checkerboard painted into the image. Only the wooden frame, soil, tiny contact shadow; NO plants, vegetables, animals, grass patch, ground plane, landscape, label, text, numbers, currency, UI, emoji, badge, decorative border, watermark or collage. Plants will be added as a separate overlay. No square icon container or illustration background. Canvas roughly 4:3, object occupies 85% width and 70% height.
```

## crop-sprouts.png

Original source: `C:/Users/1/.codex/generated_images/01a0c7cf-cdda-7c12-9ccf-d445c50f3c80/exec-b997ae15-744f-4660-97f4-21ebedb48e96.png`

Final file: `E:/petsoul-audit/petsoul/PetJourneyWeb/src/features/home/assets/living/crop-sprouts.png`

Full prompt:

```text
Use case: stylized-concept. Asset type: one transparent PNG sprite PLANT ONLY overlay for a warm 2.5D pet garden web game. Generate ONE group of 6 fresh bright green seedling plants arranged in two rows of three, all roots on one flat ground plane in a shallow rectangle viewed three-quarter from above about 35 degrees. Each is a small young vegetable sprout with two to four soft leaves and short stem, no soil attached. Rows recede naturally in perspective; front row lower and slightly bigger, rear row a little higher; group wider than tall, low centre of gravity, no tall stems. Style refined soft cinematic storybook garden, gently realistic leaf material, warm afternoon sunlight from upper left, soft natural color, tiny soft contact shadows immediately beneath stems ONLY. This sprite must overlay a separate wooden soil bed; keep plants distinct with transparent air between them. Center the compact entire group in the canvas, complete leaves not clipped, enough transparent margins. Readable at approximately 100x65 CSS pixels, restrained detail and clear silhouette. Output genuine transparent RGBA PNG alpha, no painted white or checkerboard. Only the plants and tiny translucent stem contact shadows. NO dirt, soil bed, wooden frame, planter, ground patch, lawn, scenery, animals, letters, numbers, UI, emoji, badge, border, watermark or collage. Canvas roughly 4:3.
```

## crop-tomato.png

Original source: `C:/Users/1/.codex/generated_images/01a0c7cf-cdda-7c12-9ccf-d445c50f3c80/exec-fedb1e48-3b27-435c-abf6-d81716e97be0.png`

Final file: `E:/petsoul-audit/petsoul/PetJourneyWeb/src/features/home/assets/living/crop-tomato.png`

Full prompt:

```text
Use case: stylized-concept. Asset type: one transparent PNG sprite PLANT ONLY overlay for a warm 2.5D pet garden web game. Generate ONE compact cluster of two mature tomato plants rooted on the same shallow rectangular ground plane, seen three-quarter from mildly above about 35 degrees. Rich green serrated tomato leaves, subtly hairy stems, about six clearly visible ripe red round tomatoes at different heights, tasteful small unripe green fruit optional. Plants must be low and broad, rooted together in a coherent compact crop group, no pot and no tall pole. Red fruit instantly recognizable at 110x80 CSS pixels. Match a refined soft cinematic 2.5D storybook garden: tactile believable vegetation with slightly simplified readable silhouette, warm afternoon sunlight from upper left, soft highlights and gentle leaf shadows, tiny translucent contact shadows at roots. Center full plant cluster with transparent air between leaves and generous transparent margins, no cropping. Output genuinely transparent-background RGBA PNG alpha, not white or painted checkerboard. Plant layer only: NO wooden frame, soil, dirt mound, bed, planter, ground patch, lawn, landscape, animals, letters, numbers, UI, emoji, icon container, badge, border, watermark or collage. Canvas roughly 4:3.
```
