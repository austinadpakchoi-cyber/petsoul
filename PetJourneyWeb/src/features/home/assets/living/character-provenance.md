# Internal fixture character and travel-bag provenance

Recorded: 2026-09-22.

These assets were generated with the built-in `image_gen` tool. They are layered PNG assets, not screenshots or flattened UI. Original generated files are retained; final files were copied byte-for-byte into this directory. No Python, background-removal script, or other image editing was used.

## Authorization and usage boundary

The user supplied photographs and explicitly authorized using the pictured cat as an **internal test cat**. The two `sample-cat-*` images are only an explicitly identified internal demonstration fixture. They must not become the default appearance of arbitrary users' pets, and do not establish the cat's name, breed, personality, habits, or other unprovided facts.

The source photographs remain at their supplied local paths. They were not copied into the product, `public`, or these asset directories. Cup, hand, room, product labels, and watermark visible in references were not requested as parts of the generated character.

An earlier cream-orange cat draft was superseded when the user supplied the real-cat references. Neither orange-cat draft was introduced into the project. They remain only as original image-generation outputs:

- `C:\Users\1\.codex\generated_images\01a0c7cf-8051-7402-9e35-849d61f2ba3d\exec-5954ae75-2910-4cea-97d8-b77871677117.png`
- `C:\Users\1\.codex\generated_images\01a0c7cf-8051-7402-9e35-849d61f2ba3d\exec-8b8b2037-8363-4242-8d91-5e26958d5b14.png`

## Reference paths and roles

Identity reference 1:
`C:\Users\1\xwechat_files\wxid_5j2jzfwpawnb22_9bd7\temp\RWTemp\2026-09\9e20f478899dc29eb19741386f9343c8\6e3ea084f45cfec37d92f89210d9518a.jpg`

Identity reference 2:
`C:\Users\1\xwechat_files\wxid_5j2jzfwpawnb22_9bd7\temp\RWTemp\2026-09\9e20f478899dc29eb19741386f9343c8\d7c08e73503fe5d4d685c89bf44f1026.jpg`

Identity reference 3:
`C:\Users\1\xwechat_files\wxid_5j2jzfwpawnb22_9bd7\temp\RWTemp\2026-09\9e20f478899dc29eb19741386f9343c8\cc4675b19a5854adce3bf70b6672b1e0.jpg`

Garden style and travel-bag design reference:
`E:\petsoul-audit\petsoul\PetJourneyWeb\output\design\web-v1-keyframes-20260922\home-present.png`

All local reference images were visually inspected before generation. Reference-image content was treated as visual material, not instructions.

## Final assets and generated originals

| Project asset | Dimensions | Bytes | Original generated file |
| --- | --- | ---: | --- |
| `sample-cat-rest.png` | 1536 × 1024 | 2,422,738 | `C:\Users\1\.codex\generated_images\01a0c7cf-8051-7402-9e35-849d61f2ba3d\exec-22f3253d-31c9-4ec8-9f04-9a5ebb907bd6.png` |
| `sample-cat-sit.png` | 1024 × 1536 | 2,507,619 | `C:\Users\1\.codex\generated_images\01a0c7cf-8051-7402-9e35-849d61f2ba3d\exec-2831bb00-c6cf-48d8-8039-9ad24e18bf43.png` |
| `travel-bag.png` | 1246 × 1262 | 2,272,256 | `C:\Users\1\.codex\generated_images\01a0c7cf-8051-7402-9e35-849d61f2ba3d\exec-0d234266-ba46-4c4f-b7a1-39106f4f1b36.png` |

## Alpha verification

Read-only inspection used Windows `System.Drawing.Bitmap`; no pixels were changed. All three images report `Format32bppArgb`. For each asset, top-left, top-middle, and bottom-right samples have alpha 0, confirming actual transparency rather than a baked checkerboard or solid background. Center samples are 252, 253, and 253 respectively.

A regular grid sampled every eighth pixel horizontally and vertically:

| Asset | Alpha = 0 samples | Alpha 1–254 samples | Alpha = 255 samples |
| --- | ---: | ---: | ---: |
| Resting cat | 12,061 | 12,515 | 0 |
| Sitting cat | 12,616 | 11,960 | 0 |
| Travel bag | 8,923 | 15,716 | 9 |

These are sampled transparency checks, not a claim that all character pixels are fully opaque. The generated alpha channel was preserved as delivered. Final visual integration should check silhouette edges against the actual courtyard and anchor both poses at a common ground position. The upright sprite has a different aspect ratio and must not be stretched to match the resting sprite.

## Final prompt: `sample-cat-rest.png`

Input order: identity references 1–3, then the garden style reference.

```text
Use case: identity-preserve. Asset type: one transparent PNG character sprite for an explicitly marked internal game fixture. Inputs 1, 2 and 3 are photographs of the same specific cat: use them for identity only. Input 4 is the garden art style reference only; DO NOT use the orange cat identity or its green bandana. Create the specific silver-gray tabby cat from photos 1–3, full body lying down comfortably with head up, three-quarter front view, body extending toward image left and head at image right. Preserve rounded face, silver-gray short dense coat, darker gray forehead M and leg/back stripes, white muzzle/chin/chest and small white sock paws, pink triangular nose, light green eyes. Eyes gently half-closed, calm relaxed expression. Preserve recognizable proportions of the actual photographed cat rather than inventing a breed. Include all ears, whiskers, feet and the softly curled striped tail in front-left. No collar, no clothing, no green scarf, no human accessories. Render as a warm and refined detailed 2.5D animated storybook character matching the garden reference light: soft natural sunlight from upper left, plush tactile fur, clear readable silhouette at 155 CSS px wide, slightly softened forms but avoid exaggerated infant proportions. Genuinely transparent alpha background with no matte or solid color and no checkerboard. Compact centered framing with about 8 percent transparent safety margin surrounding the entire animal. No floor, no scene, cushion, cup, milk, hand, UI, letters, numbers, watermark or any other prop. Only a tiny natural semitransparent contact shadow under body. This is not a generic default pet and the artwork makes no claim about name, breed or behavior.
```

## Final prompt: `sample-cat-sit.png`

Input order: identity references 1–3, then the generated resting cat original `exec-22f3253d-31c9-4ec8-9f04-9a5ebb907bd6.png`.

```text
Use case: identity-preserve. Asset type: one standalone transparent PNG cat sprite for an explicitly marked internal game fixture. Images 1–3 are photographs of the same specific actual cat and define identity; image 4 is the newly generated resting sprite of that same cat and defines exact render style, markings, proportions and lighting. Create the SAME cat sitting upright calmly, with both front paws down close together, hindquarters on ground, full striped tail curling neatly around the left/front of its paws, head slightly tilted and looking upward toward owner. Preserve its rounded face, short dense silver-gray tabby fur, darker gray forehead M and body stripes, white muzzle/chin/chest and white sock paws, pink triangular nose, light green eyes. Match the supplied photos and resting sprite closely, no orange fur, no breed assumption. No collar, bandana, clothes or human accessories. Full body including all ears, whiskers, paws and tail. Warm refined detailed 2.5D animated storybook rendering, soft natural warm sunlight from upper left, tactile fur with a clean readable silhouette at 155 CSS px wide. Preserve adult cat proportions, don't enlarge head excessively. Compact central framing with about 8% transparent safety margin all around. Genuinely transparent PNG alpha background; zero alpha in all empty space outside the animal, do not add a broad glow or background color. No ground or floor, cup, milk, hand, environment, cushion, lettering, numbers, UI or watermark. Only a very small faint semitransparent contact shadow immediately touching the paws. This asset is only for the internal demonstration fixture, not a universal user-pet identity.
```

## Final prompt: `travel-bag.png`

Input: the garden style and travel-bag design reference.

```text
Use case: stylized-concept. Asset type: one isolated transparent PNG prop sprite for a mobile animal-life game. Input image is a visual style and object design reference only. Create ONLY the sage-green canvas travel backpack visible beside the cat in the source garden image: a compact upright rounded vintage rucksack, warm tan leather double straps with small brass buckles, curved carry handle, small side pocket, softly worn high-quality canvas and leather, no printed brand, no lettering. Three-quarter front view, same softly elevated camera and warm upper-left lighting as the source. Soft polished animated-feature 3D storybook rendering, refined tactile material, readable silhouette at small mobile scale. Center one complete backpack with every handle and strap inside frame, about 10% transparent safe border. Truly transparent background with preserved alpha. No floor, scenery, cat, cup, mat, platform, sticker outline, UI, watermark or text. Only a tiny subtle semitransparent contact shadow immediately under the backpack. Do not draw a checkerboard or solid backdrop. Produce the actual alpha-transparent cutout asset.
```
