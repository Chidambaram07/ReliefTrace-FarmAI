# ReliefTrace

Independent-evidence verification for agricultural disaster / crop-damage relief claims (FarmwiseAI Task 1).
Claim -> validation -> plan -> photo analysis (Nova Lite) -> independent evidence (parallel) -> deterministic verification -> report -> human-review queue.

**Models:** Amazon Bedrock **Nova Lite** (photo analysis) and **Nova Micro** (optional report wording), region `ap-south-1` only.
The verification verdicts themselves are deterministic code, so the same evidence always gives the same result.

## Setup (Windows PowerShell)
```powershell
python -m pip install -r requirements-dev.txt
copy .env.example .env
mkdir data\raw, data\images, data\geo
# 1. OFFICIAL CSV  (TASK_3\Ground Truth Points\Ground_truth_Points.csv) -> data\raw\Ground_truth_Points.csv
# 2. ALL images    (TASK_4\Images\images\*.jpg)                        -> data\images\
# 3. Boundaries    (TASK_3\Administrative_Boundary\*.geojson)          -> data\geo\
python -m scripts.validate_dataset
python -m scripts.build_dataset
python -m scripts.check_bedrock          # after `aws sso login` / AWS_PROFILE: finds working Nova model IDs
python -m pytest
python -m uvicorn backend.main:app --reload      # http://localhost:8000/docs
python -m scripts.seed_demo --verify             # 4 demo claims (synthetic inputs, real photos/data)
```
`data/` is git-ignored: FarmwiseAI datasets must not be redistributed. Use the CSV inside the TASK_3/TASK_4 zips, not an
Excel-resaved copy (those have mangled dates and scientific-notation subdivisions).

## What the report contains
Every claim gets: one of five statuses (*Supported by available evidence / Partially supported / Contradictory evidence found /
Insufficient evidence / Requires further verification*), per-check findings (parcel, crop, stage, location, timing, weather,
photo vs claimed damage) each with the evidence ids, rule and limitations, a confidence index with its formula, the evidence list
(source, time, location, quality, raw reference), a timeline, missing evidence, an audit trail with model/tokens/latency, and human-review routing.
Evidence is labelled: `claim`, `source_data`, `ai_observation`, `external_evidence`, `derived`. AI output is an observation, never ground truth.

## API
| Endpoint | Purpose |
|---|---|
| `GET /api/health` | status, dataset counts, configured models (no AWS call) |
| `POST /api/claims`, `GET /api/claims[/{id}]` | claims (claimant data, unverified) |
| `POST /api/claims/{id}/images`, `.../images/from-dataset` | attach photo (upload or challenge image) |
| `POST /api/claims/{id}/images/{key}/analyze` | Nova Lite photo analysis (cached) |
| `POST /api/claims/{id}/verify?narrative=auto\|template\|off&simulate_failure=weather` | full pipeline |
| `GET /api/claims/{id}/report`, `/evidence` | latest report / evidence list |
| `GET /api/review-queue`, `POST /api/review-queue/{id}/decision` | human review |
| `GET /api/stats` | real counts only |
| `GET /api/dataset/...` | reference-data lookup with provenance |

Errors: `{"error": {"code", "message", "details", "request_id"}}`.

## Data notes (from inspection)
- 14,643 CSV rows -> 14,611 distinct records -> **3,274 images** (3,204 was the count before splitting `;`); 3,273 have a file (2,933 photo files, 129 ids have several photos).
- Official CSV dates: `timestamp` MM-DD-YYYY (39 rows DD-MM-YYYY), `image_timestamp` DD-MM-YYYY. Parsed explicitly; GT and image dates agree on every record.
- The CSV has **no disease/damage label**. None are stored or derived. Reference crop/stage labels may contain errors (Task 3/4 briefs).
- Boundary layer: village join key is `village_co` = CSV `village__1`. Layer `lgdvcode` disagrees with CSV `Village LG` for two villages, so LGD is only a fallback.
- Photos sit inside their own village polygon 92% of the time (max 70 m outside), which calibrates the location check.
- 4 images have (0,0) coordinates (treated as missing); 8 images have conflicting stages (flagged, not resolved).

## How verdicts work (backend/verification/rules.py holds every threshold)
- **Weather** (Open-Meteo archive, free, no key, reanalysis grid ~10 km, not station data): 30-day window ending the day after the incident vs the same window in the previous 10 years, as percentiles. Fetched from your machine; cached; on failure falls back to the cached copy, else the check is reported as *missing evidence* (try `simulate_failure=weather`).
- **Supported** requires: no contradiction, agreeing checks, adequate coverage, and *no major check missing* (e.g. no photo analysis, no weather).
- A photo dated before the reported incident, an explicit "no damage visible", or an outside-taluk location are high-severity contradictions.
- Pest/disease cannot be verified by weather; from one photo they are flagged low-reliability and need field inspection.
- No approved disaster-event feed exists yet: `DisasterEventAdapter` is a stub that reports "unavailable". Add adapters in `backend/evidence/adapters.py`.

## Costs
One Nova Lite call per new photo (max 3 per claim, cached by image/claim/prompt), at most one Nova Micro call per report (`narrative=template` avoids it). Tokens and latency are recorded in every report's audit trail.

## Phase 6 — Dashboard (React + Vite)

Two minimal, functional views on top of the real API (no mock data, no fabricated evidence):
- **Submit a claim** (`/`) — farmer-facing form, photo upload or attach-by-dataset-id, then runs verification.
- **Officer dashboard** (`/dashboard`) — claim list, open review queue, and a full **claim report** page: status stamp,
  confidence/coverage/agreement/evidence-quality scores, the findings ledger (verdict + rule + cited evidence per check),
  the evidence list grouped by provenance (claim / source data / AI observation / external evidence), a Leaflet map of
  every located evidence point, a timeline, missing evidence & limitations, the Nova narrative, and the full audit trail
  (model, tokens, latency, cost per step) with approve / reject / request-more-info actions.

```powershell
cd frontend
npm install
copy .env.example .env.development     # VITE_API_BASE, defaults to http://localhost:8000/api
npm run dev                             # http://localhost:5173, backend must be running separately
```
The backend's `RT_CORS_ORIGINS` in `.env` already allows `http://localhost:5173` (dev) and `:4173`/`:8080` (preview/Docker).

## Phase 8 — Docker

```powershell
# paste fresh AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN from the access portal into this shell first
docker compose up --build
```
Backend on `http://localhost:8000`, dashboard on `http://localhost:8080`. `./data` (CSV, images, geo layers) is mounted
read/write into the backend container; nothing from `data/` is baked into the image. Rebuild the dataset once inside:
```powershell
docker compose exec backend python -m scripts.build_dataset
```
AWS credentials are passed through from your shell (never stored in the image or in `docker-compose.yml`); refresh them
when the SSO session expires (~1 hour) and re-run `docker compose up`.

### Cost & scope notes for AWS deployment
- Nova Lite/Micro calls are capped at 3 images per claim and cached by (image hash, prompt, claim context); re-verifying
  a claim makes zero new model calls unless `force=true`.
- EC2/RDS are not available on this challenge account; if deploying beyond local Docker, target Lambda + API Gateway +
  S3 + DynamoDB in `ap-south-1`, using the existing `FAI-TCE-LambdaExecutionRole` (no IAM changes), with resource names
  prefixed `fai-tce-team56-`.
- Weather calls hit the free Open-Meteo archive (no key, no cost) and are cached in SQLite.
