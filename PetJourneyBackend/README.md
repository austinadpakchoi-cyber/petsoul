# PetJourney Backend

FastAPI backend scaffold for the PetSoul / PetJourney iOS prototype.

This is a real runnable backend. It stores pets, DNA, thoughts, events, feedback, postcards, device tokens, notification delivery logs, and long-term memories in SQLite, and already has provider boundaries for AMAP, Google Maps, GPT-compatible text, GPT-compatible image APIs, APNs, and future pgvector memory.

## GPT Agent Direction

The backend now treats the pet as an autonomous companion agent, not a text-template toy. The API is shaped for this behavior:

- Primary pet utterances are animal vocalizations, for example `汪呜...汪汪。呜。`.
- Human-readable meaning is stored as a hidden translation.
- iOS can reveal the meaning through `GET /api/v1/thoughts/{thought_id}/translation?pet_id=...`.
- Owner feedback saves the user's guide preference, but does not decide what the pet likes or where the pet goes.
- Default model plan:
  - `PETJOURNEY_AGENT_MODEL=gpt-5.5-2026-04-23` for the main pet agent.
  - `PETJOURNEY_AGENT_DEEP_MODEL=gpt-5.5-2026-04-23` for deeper route/personality decisions.
  - `PETJOURNEY_AGENT_FAST_MODEL=gpt-5.4-nano-2026-03-17` for low-latency lightweight turns.
  - `PETJOURNEY_TRANSLATION_MODEL=gpt-5.4-nano-2026-03-17` for translating animal vocalization into readable Chinese.
  - `PETJOURNEY_IMAGE_MODEL=gpt-image-2` for selfie/postcard image generation.
- `PETJOURNEY_AGENT_TURN_INTERVAL_SECONDS=900` throttles autonomous agent turns so iOS status polling does not create a new model response every few seconds.

Real model calls are now wired through an OpenAI-compatible relay. Copy `.env.example` to `.env`, set the dashboard client key as `OPENAI_API_KEY`, and keep `PETJOURNEY_OPENAI_BASE_URL=https://api.austinsapi.com/v1`. The backend uses Responses API first and falls back to Chat Completions if the relay does not support Responses for a model.

Image generation is isolated behind `ImageProvider`, using the same relay shape:

- `PETJOURNEY_IMAGE_BASE_URL=https://api.austinsapi.com/v1`
- `PETJOURNEY_IMAGE_API_KEY=...`
- `PETJOURNEY_IMAGE_MODEL=gpt-image-2`

The provider now supports both pure generation and reference-image generation. When a pet has an uploaded photo, postcards/selfies try the reference-image path first so "TA 发来的照片" can preserve the user's actual pet identity; if that fails, the backend falls back to pure generation, then to map/POI imagery. Keys are never exposed to iOS.

## Doubao / China Guide Research

Domestic travel-guide research is wired through Volcengine Ark / Doubao Responses API. This powers the "TA 先替你走一遍" guide layer for China destinations such as Xiamen, Gulangyu, Shanghai, Beijing, and other mainland trips.

```bash
DOUBAO_API_KEY=ark-...
PETJOURNEY_DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
PETJOURNEY_DOUBAO_GUIDE_MODEL=doubao-seed-2-1-pro-260628
PETJOURNEY_DOUBAO_REASONING_EFFORT=minimal
PETJOURNEY_DOUBAO_TIMEOUT_SECONDS=60
PETJOURNEY_TRAVEL_GUIDE_RESEARCH_PROVIDER=auto
```

Notes:

- `auto` uses Doubao for China destinations and OpenAI Web Search for overseas/worldcup flows.
- Doubao is used only by the backend; iOS never receives the Ark key.
- The request uses the Responses API `input` shape, including support for future `input_image` references.
- `reasoning.effort=minimal` is important for short guide JSON; otherwise Seed 2.1 Pro may spend the entire response budget on hidden reasoning.
- If Doubao fails or times out, the guide engine falls back to local research rules and records the reason in `research.missing_capabilities`.

## Background Life, Push, And Memory

The backend now has a `BackgroundAgentScheduler`. It can tick pets while the app is closed, advance their autonomous state, send APNs-compatible notifications, and write important turns into memory.

Core env vars:

```bash
PETJOURNEY_SCHEDULER_ENABLED=true
PETJOURNEY_SCHEDULER_INTERVAL_SECONDS=60

PETJOURNEY_APNS_ENVIRONMENT=sandbox
PETJOURNEY_APNS_TEAM_ID=...
PETJOURNEY_APNS_KEY_ID=...
PETJOURNEY_APNS_BUNDLE_ID=...
PETJOURNEY_APNS_PRIVATE_KEY_PATH=/absolute/path/AuthKey_XXXX.p8

PETJOURNEY_MEMORY_PROVIDER=sqlite
PETJOURNEY_POSTGRES_DSN=postgresql://...
PETJOURNEY_MEMORY_EMBEDDING_DIMENSIONS=64
```

APNs is provider-gated. Without Apple credentials it uses `mock-notification-provider` and still records delivery attempts for development. `PETJOURNEY_MEMORY_PROVIDER=sqlite` is the current local memory store. `PETJOURNEY_MEMORY_PROVIDER=postgres` plus `PETJOURNEY_POSTGRES_DSN` selects the Postgres provider, which tries to create the `vector` extension, `pet_memories` table, and a pgvector cosine index. If Postgres, pgvector, or the Python driver is unavailable, memory calls automatically fall back to SQLite behavior.

## Run

```bash
cd /Users/austin/Desktop/petsoul/PetJourneyBackend
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If your default `python3` does not have FastAPI installed on this machine, this environment worked during setup:

```bash
/opt/miniconda3/bin/python3.12 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## iOS-Compatible Endpoints

- `POST /api/v1/create_pet`
  - `multipart/form-data`
  - fields: `pet_name`, `pet_type`, `dna`
  - optional file: `pet_photo`
- `GET /api/v1/agent_status/{pet_id}`
- `GET /api/v1/day_plan/{pet_id}`
- `GET /api/v1/pet_dna/{pet_id}`
- `GET /api/v1/thoughts/{thought_id}/translation?pet_id={pet_id}`
- `GET /api/v1/pets/{pet_id}/city_position`
- `POST /api/v1/feedback`
  - `multipart/form-data`
  - fields: `pet_id`, `city`, `liked`

## Extra Backend-First Endpoint

- `POST /api/v1/demo/frenchie`
  - creates a demo black French bulldog agent named `小黑`.
  - uses `/media/demo/frenchie-profile.png` as the uploaded identity photo.
  - immediately creates a first postcard with `/media/demo/frenchie-netcafe-postcard.png`.
  - intended for iOS demos where the pet has already sent a photo from the other world.
- `GET /api/v1/pets/{pet_id}/route_plan`
  - returns the current mock route/POI plan.
  - intended to become the AMAP/Google Maps route + POI contract.
- `GET /api/v1/pets/{pet_id}/journey_plan`
  - returns the richer route contract with POI stops, scheduled transport, route segments, and guide candidates.
- `GET /api/v1/pets/{pet_id}/pet_guide`
  - calls `PetGuideEngine` with the current `JourneyPlan`.
  - uses the GPT-compatible relay when configured, grounded in real AMAP guide candidates for Xiamen/China cities.
  - returns surface animal language plus a readable Chinese translation, route theme, mood, chosen stops, dwell time, rating/photo metadata, and the autonomy note.
- `GET /api/v1/pets/{pet_id}/world_snapshot`
  - returns the current simulated-world state for the pet.
  - combines `JourneyPlan`, scheduled transport, stop windows, real elapsed time, activity progress, current coordinates, energy/happiness/curiosity, and world rules.
  - intended to drive the immersive communicator map so iOS does not infer local movement with a separate private model.
- `GET /api/v1/pets/{pet_id}/street_rank?theme=coffee`
  - returns a PetSoul street-rank list grounded in AMAP POI 2.0 data.
  - themes include `coffee`, `night`, `photo`, `rain`, and `street`.
  - AMAP does not currently expose a public "扫街榜" Web API, so this is a PetSoul ranking layer over AMAP POI weighted order, rating, photos, distance, weather, and pet DNA.
- `GET /api/v1/pets/{pet_id}/static_map`
  - fetches an AMAP static map image through the backend and stores it under `/media/static_maps`.
  - never returns the raw AMAP key to iOS.
- `GET /api/v1/amap/input_tips?keywords=咖啡&city=厦门`
  - exposes AMAP input tips for future search boxes and destination pickers.
- `GET /api/v1/amap/reverse_geocode?lat=24.4798&lng=118.0894`
  - exposes AMAP reverse geocoding for turning coordinates into readable place context.
- `GET /api/v1/google/config`
  - returns Google Maps provider status for Places, Routes, and Geocoding.
- `GET /api/v1/google/reverse_geocode?lat=35.0116&lng=135.7681`
  - exposes backend-side Google reverse geocoding for overseas coordinates.
- `GET /api/v1/agent_brain/config`
  - returns the current LLM/model defaults and whether remote calls are enabled.
- `GET /api/v1/image_provider/config`
  - returns the image model/provider configuration without exposing the key.
- `GET /api/v1/travel_research/config`
  - returns Doubao/OpenAI guide-research configuration without exposing keys.
- `GET /api/v1/memory/config`
  - returns the current memory provider and embedding settings.
- `GET /api/v1/notifications/config`
  - returns APNs/mock notification provider status.
- `GET /api/v1/scheduler/config`
  - returns scheduler status, interval, notification provider, and memory provider.
- `POST /api/v1/scheduler/tick`
  - manually advances all pets once; useful for testing background life without waiting.
- `POST /api/v1/push/register`
  - JSON body: `pet_id`, `device_token`, `platform`, `environment`.
  - stores iOS device tokens so the scheduler can notify when TA has a new thought/postcard.
- `POST /api/v1/push/unregister`
  - unregisters a device token.
- `GET /api/v1/pets/{pet_id}/notifications`
  - returns push delivery logs.
- `GET /api/v1/pets/{pet_id}/memories`
  - returns long-term memories for the pet.
- `POST /api/v1/pets/{pet_id}/memories`
  - adds a manual memory note.
- `POST /api/v1/pets/{pet_id}/memories/search`
  - searches memories using the current embedding provider.
- `POST /api/v1/pets/{pet_id}/generate_selfie`
  - creates a new autonomous postcard/selfie for the pet and writes it into memory.

AMAP Web service can be enabled without changing the rest of the backend:

```bash
PETJOURNEY_MAP_PROVIDER=amap
AMAP_API_KEY=...
```

When enabled, the backend uses AMAP POI 2.0 nearby search for China-city journey stops, requests business/photo fields, sorts by AMAP's weighted recommendation order, then applies a PetSoul guide score. Returned places can include rating, distance, business area, photo URL, guide score, and guide reason. If AMAP is unavailable, it falls back to the mock map provider.

The same AMAP Web service key is also used by `AMapWeatherProvider` for live weather:

- endpoint: `/v3/weather/weatherInfo`
- first wired city: `厦门` / `350200`
- cache: 10 minutes per city, so iOS polling does not repeatedly hit the weather API
- consumers: `agent_status`, `world_snapshot`, agent brain context, postcards, and image prompts
- fallback: non-China/unsupported cities keep their local mock weather copy until an overseas weather provider is added

Quick demo seed:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/demo/frenchie
```

## Provider Plan

- China maps: AMAP POI 2.0 guide candidates are wired; walking/transit route providers are the next layer.
- China weather: AMAP live weather is wired through `AMapWeatherProvider`.
- Overseas weather: Google Weather API current conditions are wired through `GoogleWeatherProvider`; when both AMAP and Google keys are present, `HybridWeatherProvider` uses AMAP for China cities and Google for overseas supported regions.
- China routing: AMAP walking/driving route planning is wired into `JourneyPlan.route_segments`; local segments can now include real distance, duration, and polyline.
- China street rank: PetSoul street-rank is wired over AMAP POI 2.0. Official AMAP "扫街榜" app content is not exposed as a documented public Web API.
- AMAP utility APIs: input tips, reverse geocoding, and backend-fetched static maps are wired for future UI/search/postcard use.
- Overseas maps: Google Places API (New), Routes API, and Geocoding API are wired through `GoogleMapsServiceClient`. With both AMAP and Google keys configured, `HybridMapProvider` uses AMAP for China-city POI and Google for overseas POI/routes.
- Overseas weather note: Google Weather API coverage excludes unsupported countries/regions such as Japan and Korea; unsupported locations keep the local fallback weather copy instead of failing the agent flow.
- Companion text: `OpenAIPetAgentBrain` and `PetGuideEngine` use the OpenAI-compatible relay for thoughts, translations, and pet-authored city guide planning.
- China guide research: `TravelGuideResearchEngine` calls Volcengine Ark / Doubao Responses API for China destinations when `DOUBAO_API_KEY` is configured, and feeds the resulting strategy/findings/sources into `TravelQuestGuide`.
- Image/selfie: `ImageProvider` can call OpenAI-compatible `/images/generations` and `/images/edits` relay paths, parse either `b64_json` or a temporary image `url`, and use the pet photo as a reference image when available.
- Push/scheduler: `BackgroundAgentScheduler` advances pets outside iOS foreground sessions and dispatches APNs-compatible notifications when new thoughts/postcards appear.
- Long-term memory: `MemoryStore` records identity DNA, owner preference signals, postcards, and scheduler turns. SQLite is active by default; Postgres/pgvector is implemented behind the same API and activates when `PETJOURNEY_MEMORY_PROVIDER=postgres` and `PETJOURNEY_POSTGRES_DSN` are configured.
- Transport reality: `JourneyPlan.scheduled_transport` now carries mode-specific transport legs with status, scheduled departure/arrival, origin/destination coordinates, service labels, progress, and a reality level. The current provider is a mock scheduled transport layer; future providers can replace it with real flight, rail, transit, and route schedule sources without changing the iOS contract.
- World simulation: `WorldSimulationEngine` turns plans into a live `WorldSimulationSnapshot`, choosing the current activity from stop windows and active transport while enforcing no-teleport, real-time, and pet-autonomy rules.

The app currently uses `PETJOURNEY_PROVIDER_MODE=mock`. When real APIs are ready, switch the mode to `remote` and implement the placeholder provider classes in `app/providers.py`.
LLM calls are controlled separately through `PETJOURNEY_LLM_PROVIDER=openai`, so maps can remain mock while the pet agent uses the relay.

## Test

```bash
cd /Users/austin/Desktop/petsoul/PetJourneyBackend
/opt/miniconda3/bin/python3.12 -m unittest discover -s tests
```
