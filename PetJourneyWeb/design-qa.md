# PetSoul living scenes — internal prototype QA

Date: 2026-09-22, Asia/Shanghai. Window: `codex-20260922-131657-petsoul-visual-r7k`.

final result: passed

This result is scoped to the **internal, fixture-backed interactive sample and the revised frontend components**, not the whole product, real-account departure, live provider maps, personalized pet generation, or production release.

## Source truth and normalization

- Source visual direction: `output/design/web-v1-keyframes-20260922/{home-present,home-away,journey-cat222}.png`, each 853×1844. Also the user's subsequent written critique (closer porch, larger pet, explicit state, DOM controls, no generated navigation map) and five newly supplied silver-tabby photos used only for internal character identity.
- Source normalized to 390×844 CSS px, contain fit, no selective cropping in full-view boards; native aspect-ratio difference is < 1 px at this size. Runtime screenshots are 390×844 at screenshot scale `css` (1 output pixel / CSS px).
- Currency, name, crops, journey origin, remaining time and media title intentionally come from existing fixture services, **not the generated mock's numbers**. The photo-backed silver cat intentionally replaces the orange draft. The fixture remains named 团子 with an explicit explanation outside the artboard; no name is inferred from the photos.
- Full comparison inputs (source left, runtime right): `output/playwright/living-compare-pass1.png`, `living-compare-target-home.png`, `living-compare-target-away.png`, `living-compare-target-journey.png` (780×844). Both images were opened together as combined boards, not judged from paths.
- Focused comparison: `living-compare-detail.png` (780×310), source porch/garden y280–590 vs revised closer camera y220–530. Inspected pet identity/ground contact, texture/alpha, soil/plant layers, cup and mailbox affordance.
- Same-viewport actual frontend before/after: `living-before-home-390.png` / `living-away-final-390.png`; combined `living-before-after-home.png`. Both are away-state fixture /home presentations. Before is this round's original runtime, not a concept mock.

## Findings and iteration history

1. [P1, fixed] Scene-contained pet action sheet was underneath the participation card. Browser click failed because the card intercepted pointer events. Sheet now uses a body portal and preserves Escape/focus restoration; actual click to sitting pose succeeded. Evidence: `living-room-sit-390.png`, portal/focus regression test.
2. [P2, fixed] Audio sheet initially hid the vehicle. Initial `living-media-synced-390.png`; map height now responds to an open sheet, keeping the moving vehicle and attached badge above it. Post-fix: `living-media-synced-final-390.png`, `living-media-paused-390.png`.
3. [P2, fixed] Header used a generic blue avatar despite the internal character being photo-backed. Initial `living-home-first-390.png` / comparison pass1. Internal composition now supplies the matching sprite thumbnail; other pets retain their own photo. Final home board verifies the replacement.
4. [P2, fixed] The source home's persistent cup had disappeared during background separation. Added a separate ordinary empty ceramic cup; present and away snapshots both retain it. It is **not a personal-memory claim**. Final home/away boards and DOM test show cup count 1 with away pet/bag counts 0.
5. [P2, fixed] Dark theme inherited light text onto the fixed warm-paper participation card. Added fixed paper ink and a dark-theme button override; `living-home-dark-390.png` shows readable text and reduced-motion mode.
6. [P2, fixed] Narrow journey heading repeated “示意” beside both station names, creating an orphaned suffix. Removed only those redundant inline suffixes; map/data-source notices remain visible.
7. [P1, fixed] Same-kind media changes could retain the prior source because edition was overwritten before comparison. Source identity is now independent of UI state. Added real-playing-event and join-ack gates, stale event/leave guards, failed-join handling, and video-collapse cleanup. Four new player tests cover these boundaries; actual audio/video were checked separately in Chromium.

No remaining actionable P0/P1/P2 findings within this sample's stated scope. Small polish left (P3): paused state currently has both a status chip and a sentence; individual crop varieties other than tomato use neutral leaf imagery plus the authoritative crop label, not invented exact fruit illustrations.

## Five fidelity surfaces

- **Fonts:** existing system Chinese sans stack retained (Windows falls back to Microsoft YaHei/Segoe UI); no rasterized labels. Home name 19 px, contextual heading 18 px, body 12–15 px. Secondary plot tags are deliberately smaller and supplemented by full accessible button labels. Source's handwritten illustration marks were not used as functional text.
- **Spacing/layout:** porch is closer, the resting cat's visible width approximately 37% of scene width; house, cushion and props share the closer composition. One contextual first-screen card, not duplicate identity cards. House door and explicit room switch both work. No horizontal overflow at 320×844, 390×844, 768×1024 and 1440×900. Desktop retains the same scene aspect ratio rather than cropping the pet away from the cushion.
- **Colors/tokens:** existing warm surface/leaf/ink tokens retained for app controls, sheets and maps; fixed warm scene/paper colors for the illustrated world. State green is used for available harvest/synced status, not fake success. Dark chrome does not add a sad filter to an away home. No new theme/shared-token ownership change.
- **Images:** nine independent original layers: courtyard, room, rest cat, sitting cat, travel bag, cup, soil, sprouts, ripe tomato. All object/character PNGs have real alpha, no checkerboard. WebP derivatives preserve alpha and aspect ratio, original PNGs/provenance retained. No cat or crops are painted into the fixed courtyard. No generated geography used as a navigable map.
- **Copy/content:** current fixture wallet/inventory/stages/session title/time used unchanged; unavailable capabilities are not invented. “收获→仓库” is distinct from selling/orders→wallet. Character photo permission is internal-only and not a universal account identity. Map, sample controls and media origin are explicitly labeled.

## Verified interactions

### Browser (existing fixture Vite 5287, Playwright `petsoul-visual`)

- Harvest from the scene: `star_tomato` ripe→harvested; pantry 3→6; wallet **120→120**. Repeated in final run. Screenshot `living-harvest-390.png`.
- Away control: pet 0, bag 0, cup 1; identical courtyard background URL. Same sunlight/space. Screenshot `living-away-final-390.png`.
- Room toggle and pet action: actual button click changes rest→sit; `living-room-390.png`, `living-room-sit-390.png`.
- Music badge→session `fx-ms-flight`: actual HTMLAudioElement `paused=false`, `readyState=4`, time 10.003 s, source `/fixtures/media/fixture-melody.m4a`. Mode synced follows real playing plus acknowledgement, not click alone.
- Joint pause: actual audio `paused=true`, time 11.061 s stayed within 0.1 s over 4 s; vehicle moved (+0.0839538574 px, -0.0764465332 px) over the same interval. This intentionally small movement follows the existing 3-hour fixture timeline; no speed-up. Reopening through mini dock still used `fx-ms-flight`.
- Resume: subsequent audio playing confirmed, narrow-screen run had time 11.9516 s, paused=false, readyState=4. Closing the audio sheet retained audio/dock.
- Video: real local test video paused=false, readyState=4, time 12.102643 s, intrinsic width 480. Collapsing sheet paused local video and changed dock message accordingly. `living-video-390.png`.
- Missing-media test scenario: actual load/play failure rendered “播放失败” and “重试加入”, not synced. `living-media-failed-390.png`.
- 320-px audio panel: no horizontal overflow; controls usable. `living-media-320.png`.
- A fresh normal session's console contained only React's development notice, no application errors. Earlier favicon 404 fixed for the sample entry. Missing-media scenario errors are intentional. A Playwright session later returned about:blank; reopened the local sample and repeated final checks, not attributed to an app defect.

### Code checks, 2026-09-22 15:17 +08:00 (final rerun)

- `npm run typecheck`: passed.
- `npm test`: **10 test files, 41 tests passed**. 10 new tests (6 living-scene/time/farm, 4 player). Existing jsdom media load/pause not-implemented warnings remain in old participation tests; those are not browser-playback proof.
- `npm run build`: passed, 172 modules. Production output contains courtyard/room/crops/cup but **not the sample-cat or travel-bag assets**, because the sample composition is not imported by app routes.
- Time regression: 16:20 UTC+8→19:43 UTC+9, now 17:00 UTC+8: elapsed 40/143 = 27.97%, remaining 103 min, common effective time anchor. Time progress does not claim real GPS distance.
- Kept session gate, API service interfaces, feature slots, map adapter/attribution, and shared clock/contracts intact. No backend change or deployment.
- Final code review separated the away note from the confirmed-object note so one cannot open the other's content when both exist. Typecheck, 41 tests and build rerun successfully afterward. Normal sample entry reopened and evidence gallery HTTP 200 verified.

## Unproven / outside this result

- Live authenticated user end-to-end, real departure deduction, provider map/flight data, production persistence, multi-device media sync/accounted companionship. Only fixture/local browser evidence here.
- Personalized live full-body sprites: no such field in the current HomeSnapshot contract; live pets keep their own photo, never the internal cat.
- Confirmed note→specific object sprite mapping: absent from current contract. Existing confirmed `welcome.details` can be shown; no note is fabricated and no blue blanket/diet/habit inferred from photos. Further backend/asset contract coordination is needed for that production feature.
- Performance under slow mobile networks/device GPUs and real touch devices beyond Chromium viewport emulation.
- Claude's concurrent backend/DNA contract work began at 15:06; this report records the checks above, not future schema changes or that task's outcome.

## Handoff

- Interactive: `http://127.0.0.1:5287/output/design/living-sample/index.html`
- Evidence gallery: `http://127.0.0.1:5287/output/design/living-sample/evidence.html`
- Main updated fixture app: `http://127.0.0.1:5287/home`
- Existing Vite 5287/5288 untouched; no newly started server, no new DB, no paid project-provider call, no commit or publish.

---

## Unified life UI follow-up — 2026-09-22 15:34–15:49 +08:00

### Audit scope and reference boundary

- **Captured current runtime:** Codex in-app browser on the existing fixture sample (`5287`) at the same mobile composition. The pre-change screen had a scene garden plus a second full “菜园” card/grid beneath it; the post-change screen has the scene as the only garden index and opens one bottom sheet on plot selection.
- **iOS source reference, not a visual clone:** reviewed `PetJourneyIOS/PetJourneyIOS/Design/DesignTokens.swift`, `Views/Components/SoftCard.swift`, `ToastView.swift`, and the map sheet call sites. Reused only the design principles: 18 px card radius/page rhythm, porcelain/mist/paper/deep-ink surface roles, and contextual bottom sheets. No iOS screenshot, source art, copy, balance, map or private data was copied.
- **Known limit:** this follow-up unifies the three living-scene surfaces (home/garden, journey/map, companion media). It does not claim that every later support page in the product has been redesigned.

### Fixed findings

1. **[P1, fixed] Duplicate farm UI diluted the world.** `FarmPanel` no longer renders a second full card grid below HomeScene. The actual scene plots remain keyboard-accessible buttons; selection opens the preserved business action in a contextual `ps-garden-sheet`.
2. **[P1, fixed] Farming had no tactile stage treatment.** Empty/harvested soil, growing crop sway, ripe crop lift/glow, and a visible success receipt now use real layer images plus CSS motion. The sheet uses the same true `PlotSummary`, pantry and guard data as before; a successful harvest changed fixture pantry 3→6 and kept wallet 120→120.
3. **[P1, fixed] The internal cat read as illustration/static.** `LivingSample` now uses two new, alpha-preserving, photorealistic WebP cutouts based on the user-authorized internal test photo references: resting and sitting. The normal application route still uses the real account `photo_url`; the asset provenance explicitly forbids treating the fixture label as a real name or copying the source photos. A 5.6 s breathing/settling motion is disabled with `prefers-reduced-motion`.
4. **[P2, fixed] Journey and media did not share the material system.** Journey summary, map corner radius, fixture disclosure, media heading/actions, media sheet and mini dock now use the same warm-paper/porcelain border, 18 px radius and restrained shadow rules as home. Interaction, vehicle movement and source warnings were not changed.

### Browser verification in this follow-up

- Home load: exactly three stateful scene plot buttons; no legacy `garden` card/grid in the accessibility tree. Ripe, growing, and empty labels are rendered from the current fixture stage.
- Plot drawer: selected ripe tomato opened a sheet with real tomato/soil artwork, `收获`, inventory and guard state. After action settled, the same plot read `空出来啦，可以种植`; receipt said `星星番茄 ×3 进了仓库`; pantry read 6 and wallet remained 120.
- Cat: verified resting photo cutout in the porch scene; `陪 TA 坐一会儿` visibly changed it to the independent sitting cutout. It is still labelled “内部角色动作示例，不改变宠物真实状态”.
- Journey: Cat222's vehicle remained visible with its moving music badge; the unified audio sheet retained “演示行程” / “内部测试音视频” provenance labels and the no-fake-together state before join.

### Code checks, 2026-09-22 15:49 +08:00

- `npm run typecheck`: passed.
- `npm test`: **10 files / 41 tests passed**. Existing JSDOM HTMLMediaElement warnings are test-environment limitations, not playback proof.
- `npm run build`: passed (172 transformed modules). The new photo-cat assets remain sample-only and therefore are absent from the normal production app bundle.
