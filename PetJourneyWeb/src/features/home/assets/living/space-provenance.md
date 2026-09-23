# Living space background provenance

Generated on 2026-09-22 with the built-in `imagegen` tool, one call per background. The input keyframe was used only as a visual architectural/material reference. No interface or business state is baked into either background. Originals remain at their generated-image paths; final PNG files were copied into this directory without overwriting existing assets.

## Courtyard

- Final file: `courtyard-base.png`
- Dimensions: 964 × 1632 px
- File size: 3,072,656 bytes
- Source: `C:/Users/1/.codex/generated_images/01a0c7cf-447e-7cb3-b2ef-5917f060797d/exec-f566c9d1-0fef-4f78-a325-f5f2392d6846.png`
- Reference: `E:/petsoul-audit/petsoul/PetJourneyWeb/output/design/web-v1-keyframes-20260922/home-present.png`
- Approximate observed layer anchors, measured as percentages of the complete image: empty cushion center `(50%, 47%)`, width `50%`; available grass region `x 0–58%, y 65–95%`; closed mailbox center `(87%, 59%)`.
- Constraints checked visually: no characters, UI, text, numbers, crops, raised beds, backpack, notes or letters. The cottage, porch, tree, closed mailbox and empty cushion are static architecture. Crop, pet and state layers must be added separately by the frontend.
- Limitations: the mailbox is higher than the requested `(84%, 68%)`; use the observed anchor when placing its interactive region. These are visually estimated anchors and still need browser layout verification. The source PNG should be compressed for runtime use.

### Complete prompt

```text
Use case: precise-object-edit.
Asset type: production background layer for a mobile living-pet garden scene. Image 1 is the architectural and lighting reference, not a UI to reproduce.
Primary request: Recompose this same small cottage and courtyard as a clean EMPTY background, portrait aspect ratio 390:660 (13:22), without any interface. Bring the camera closer to the porch so the pet area will be visually prominent when composited later.
Keep: the charming moss-green tiled roof, warm wooden round-window door, plaster and timber walls, left leafy tree, cozy porch, cottage garden and warm animated-feature-film materials. Keep one closed green-and-cream mailbox attached to its post at the right side. Soft sunlight from upper left. Original painterly 2.5D animal-storybook world.
Composition: a large EMPTY oval woven fabric pet cushion is centered at x=50%, y=47% of the full image. The cushion spans about 43% of image width; its visible top surface must have enough empty space for a separately rendered pet. Porch horizontal plane must be readable. The door and roof occupy the upper half. A patch of clean grass at lower-left x=6–55%, y=63–91% is empty and unobstructed, ready for three independent garden-bed sprites. One short stone path leads from lower-right/center to porch, do not stretch it into repeated foreground. Closed mailbox center around x=84%, y=68%; flowers may frame the edges but must not cover the empty grass or cushion.
Remove ALL UI cards, header, footer, navigation, labels, text, badges, numbers, status chips, icons, watermarks and currency. Remove the cat and all animals, humans, backpack, cup, luggage, loose paper, notes, envelopes, crops, raised garden beds and vegetable plants. No letters or readable marks. No blurred foreground flowers; keep the whole useful scene clear. No sky-dominant empty space. A clean, coherent background for interactive DOM layers, edge to edge, no border.
```

## Room

- Final file: `room-base.png`
- Dimensions: 964 × 1631 px
- File size: 2,432,879 bytes
- Source: `C:/Users/1/.codex/generated_images/01a0c7cf-447e-7cb3-b2ef-5917f060797d/exec-94892392-3f03-44ba-a62d-c66acfea0b1c.png`
- Reference: the courtyard source PNG above, used for cottage palette, materials and lighting continuity.
- Approximate observed layer anchors: empty bed center `(50%, 59%)`, width `82%`; empty display cabinet occupies the upper-right with three open shelves.
- Constraints checked visually: no pets, people, UI, text, numbers, crops, luggage, correspondence or personal memory objects. Empty shelves are intended to receive separately rendered keepsakes.
- Limitations: the bed is materially wider than the requested 52%, although its center matches the intended position. Start a separate pet at approximately 33–38% scene width and its sitting/lying baseline around `y 60%`, then verify the contact relationship in the browser. These are visually estimated anchors. The source PNG should be compressed for runtime use.

### Complete prompt

```text
Use case: illustration-story.
Asset type: production EMPTY room background layer for a living-pet mobile web scene. Image 1 is a reference for the SAME cottage's warm materials, color palette and lighting, not an edit target.
Primary request: Show the inside of this exact cozy small timber-and-plaster cottage as a complete intimate pet-scale room, with no characters or interface, in portrait aspect ratio 390:660 (13:22).
Scene: warm honey timber floorboards and beams, cream plaster walls, an arched wood-framed window on the left letting soft sunlight in with a small glimpse of the same green garden, a small simple wooden table at back left with one plain empty ceramic cup, and a wooden display cabinet at back right with empty open shelves ready for future independent keepsake layers. Furniture supports animal scale, feels carefully made and comfortably used. No personal photographs, letters, books with text, or narrative objects.
Composition: a large EMPTY oval low woven fabric pet bed on the wood floor centered at x=50%, y=60% of the full image, about 52% image width. An unobstructed top surface will receive a separately rendered pet, and the bed must read clearly in a 390px scene. Camera is low enough for intimacy and slightly downward enough to see the floor and bed. Window, table and cabinet are fully visible within a coherent small room, not isolated objects. Subtle open floor in the lower third, no excessive empty floor or obstructing foreground. Similar soft perspective to reference porch. Sunlight comes from upper-left to agree with the separate pet layer. Keep the bed separated visually from cabinet and table.
Style: refined original 2.5D animated-feature-film animal-life storybook, soft warm sunlight, tactile woven textile, rounded solid wood, gentle ambient shadows, muted moss green accents consistent with the garden house. Warm and inviting, high craft, no plastic sheen.
Constraints: absolutely no pets, animals, humans, characters, faces, body parts, text, words, numbers, UI, buttons, labels, header, footer, frames, watermark, currency, logos, backpacks, envelopes, loose paper, photograph, personal memory object or crops. Do not put any shadow shaped like an animal. Background edge to edge. No strong depth-of-field blur; scene remains readable as interactive architecture.
```

## Ordinary cup

- Final file: `ordinary-cup.png`
- Dimensions: 1254 × 1254 px
- File size: 933,549 bytes
- Source: `C:/Users/1/.codex/generated_images/01a0c7cf-447e-7cb3-b2ef-5917f060797d/exec-ac44d486-20fe-4947-a290-f1196b7db812.png`
- Generated in one built-in `imagegen` call, with no input image. The prompt follows the same established cottage material and lighting direction.
- Intended layer: static ordinary porch decor, retained in both at-home and away states. Render at approximately 32 CSS pixels and anchor its bottom to the porch plane. It does not represent a user's actual belongings, a branded cup, a pet's diet or a personal habit.
- Alpha validation: PNG decoded as `Format32bppArgb`; 790,518 fully transparent pixels; background corner `(0,0)` and handle opening sample `(1010,600)` both have alpha 0. The tool's body pixels are typically alpha 253; the original generated alpha is preserved. The handle hole is genuinely transparent, with no baked checkerboard.
- Visual check: one complete empty cream ceramic mug with a generic muted green leaf motif, handle on the right, slight elevated three-quarter view, upper-left warm light. No text, logo, beverage, steam, saucer, scene or UI.
- Limitations: minor soft alpha at the silhouette is present in the original generated asset; check the 32-pixel composite on its actual porch background. PNG has generous transparent padding, so tune the image box against the visible cup rather than assuming every pixel is occupied.

### Complete prompt

```text
Use case: illustration-story.
Asset type: one transparent PNG game prop sprite for the PetSoul cottage porch, composited as a 32 CSS pixel ordinary household object.
Primary request: exactly ONE plain cream-colored ceramic mug, the complete mug and curved handle fully visible, centered and occupying most of the canvas with a small transparent margin. Three-quarter view slightly from above, handle on the right. A very small pale sage green generic leaf motif is allowed, without lettering or recognizable marks. The cup is empty with a clearly visible interior and rim; no steam, no beverage, no contents.
Style: original refined 2.5D animated-feature-film storybook material, softly rounded solid ceramic, tactile but simple shape that reads at 32 pixels. Soft warm sunlight from upper left, gentle self-shading, subtle cream and muted sage colors, compatible with a warm timber cottage porch. Keep the silhouette and handle hole clean and legible.
Constraints: genuinely transparent alpha background throughout outside the mug, including inside the handle hole. No checkered pattern rendered as pixels, no white background, no colored background, no floor, no table, no cast shadow outside the object, no scene. No brand, logo, letters, numbers, watermark, cat, pet, person, paw print, saucer, spoon, food, backpack, additional object or UI. This is generic static home decor and does not signify any diet or personal habit.
```
