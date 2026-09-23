# Internal test character — photo cutouts v2

## Scope

`sample-cat-photo-rest-v2.webp` and `sample-cat-photo-sit-v2.webp` are internal-only character layers consumed solely by `LivingSample`. They are never imported by the normal app route, and are not an assertion about any real account or pet.

## Source and processing

The user supplied the reference photographs in this conversation and explicitly authorized their use as an internal test cat. The original photographs were not copied into this repository or `public`.

Built-in ImageGen was used in `identity-preserve` mode on 2026-09-22. The reference role was to retain a young silver-gray tabby's visible markings, white chest/paws, muted green eyes and pink nose. Two transparent PNG cutouts were generated: a resting pose and a seated, attentive pose. They were then mechanically downsampled with local FFmpeg to alpha-preserving WebP (`yuva420p`): 768×512 and 640×854 respectively.

## Prompt constraints

- photorealistic camera-photo cutout, not illustration, cartoon or 3D render;
- isolated transparent background, no props, text or watermark;
- no inferred name, breed, habits, food preference or relationship;
- only a subtle CSS breathing / settling treatment, disabled by `prefers-reduced-motion`.

## Deliberate boundary

These files are demonstration art, not a user-photo upload feature and not a replacement for a real user's `photo_url`. The fixture label “团子” remains fixture data only; it does not name the cat in the reference photos.
