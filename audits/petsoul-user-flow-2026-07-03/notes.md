# PetSoul User-Flow Audit Notes

Date: 2026-07-03
Surface: PetJourney iOS prototype
Evidence folder: /Users/austin/Desktop/petsoul/audits/petsoul-user-flow-2026-07-03

## Captured Steps

1. Public world / first launch
   - Screenshot: 01-public-world.png
   - Health: promising but still too abstract.
   - The first sentence, "也许 TA 正在世界某个角落", is emotionally right and gives the user the correct mental model.
   - The bottom card has a clear entry action, "寻找我的 TA".
   - The globe surface currently feels more like a grey simulation grid than a living, real-world planet. It does not yet visually sell "there are many pets alive in this parallel world".
   - The stats create credibility but also make the product feel slightly dashboard-like before the user has felt the story.

2. Notification permission interruption
   - Screenshot: 02-notification-permission-blocker.png
   - Health: high-risk timing.
   - The system prompt appears before the user has seen enough value in the personal journey.
   - This breaks the emotional reveal: instead of meeting the pet, the user must make a system decision.
   - Better timing: request notifications after the first postcard, first photo, or after the user explicitly turns on "TA 有消息时提醒我".

3. Journey map compact state
   - Screenshot: 03-journey-map-after-permission.png
   - Health: functionally useful, emotionally close, but still tool-heavy.
   - The map is much more believable than the earlier custom globe work. Route lines, real roads, and water boundaries make the world feel grounded.
   - The pet marker and compact status card communicate "TA is here" quickly.
   - The top area has many floating controls. This makes the screen feel like a map/navigation tool instead of a quiet soul communicator.
   - The compact state text can become awkward when place names are long or mixed-language, such as "LONE STAR孤星汉堡". It needs a more graceful place-name display rule.
   - The bottom card has a pixel activity animation, which is a good direction, but the map itself still does not show much pet personality beyond the marker.

4. Journey expanded state
   - Screenshot: 04-journey-expanded-card.png
   - Health: not fully captured.
   - Simulator click automation was blocked by macOS accessibility restrictions, so this screenshot remains compact.
   - Expanded-state assessment is based on current code structure, not a fresh captured screen.
   - The code now contains "TA 的小想法", pet transmission, owner message composer, receipts, photo mission, route summary, and action buttons inside one expanded panel. The content is useful, but likely risks becoming too dense on small phones.

## UX Findings

1. The core concept is finally visible, but not fully embodied.
   - The product wants to be "TA is living in another world".
   - Current UI still often says this through cards and labels, while the map and pet movement do not yet carry enough of that feeling by themselves.

2. First launch should be less statistical and more magical.
   - Public world stats are useful, but they appear before the user has bonded with the premise.
   - Consider replacing or delaying the stat row with a small live story ticker: "一只小猫刚在东京便利店门口躲雨", "一只狗在厦门海边等风".

3. Permission request is too early.
   - Ask after a value moment, not at the journey reveal.

4. Onboarding copy should stop exposing prototype mechanics.
   - Current code includes lines like "第一版会做模拟照片识别" and "先不做真实 AI 判断".
   - User-facing copy should preserve the ritual. Internal truth can live in docs, not the app.

5. Main map hierarchy should become calmer.
   - Keep map full-bleed.
   - Keep one primary emotional status card.
   - Move secondary controls into one compact radial/menu or bottom sheet.
   - The current floating controls are useful for debugging and power use, but noisy for emotional companionship.

6. Pet autonomy needs a visible rhythm.
   - "TA 的小想法" is the right new module.
   - It should be short, future-facing, and explain autonomy: "TA 可能会在这里多待 20 分钟", "TA 不一定会采纳建议，但记住了".

7. Place and time plausibility need strict guardrails.
   - The app should avoid strange meal/place choices and abrupt transitions.
   - Long mixed-language place names need friendly display names.
   - Morning food, late-night activities, travel time, walking speed, and rest duration should all be governed by the life engine.

8. Photos/postcards are the strongest emotional payoff, so they need to feel persistent and non-repetitive.
   - Receiving a photo should not reset when a card collapses.
   - Generated images should use the pet's uploaded photo as reference for second creation, not generic pet images or cutout composition.
   - Postcard text should vary by place, time, mood, and recent memory.

## Accessibility Risks

1. Some text is low-contrast over translucent panels and map backgrounds.
2. Several icon-only controls are visually ambiguous without text labels, even if accessibility labels exist in code.
3. Dense bottom-sheet content may become hard to read with larger Dynamic Type.
4. Motion and pulsing effects should respect Reduce Motion.
5. Screenshot-only review cannot verify VoiceOver reading order, focus order, or keyboard behavior.

## Recommended Priority

1. Delay notification permission until the first meaningful message/photo.
2. Remove prototype/internal wording from onboarding.
3. Simplify the main map HUD and reduce top floating controls.
4. Make "TA 的小想法" the main emotional explanation layer.
5. Add stricter life-engine rules for time, food, travel duration, and place naming.
6. Upgrade public world from abstract icons to anchored mini-life events.
7. Treat photos/postcards as persistent, generated, reference-based emotional artifacts.

