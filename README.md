# TrimAURA

High-speed, template-driven **16:9 → 9:16** short-form video reframing, captioning
and publishing engine.

Upload a long-form recording or paste a link, and TrimAURA transcribes it, picks
the moments worth clipping, reframes each to vertical with face tracking, burns
in animated word-by-word captions, and hands you a publish kit with per-platform
captions and upload links.

Built mobile-first — the PWA drives it from a phone while all heavy work
(transcode, transcription, hook selection, FFmpeg render) runs on serverless
containers.

## Stack

| Layer | |
|---|---|
| API | FastAPI + SQLModel |
| Database | Supabase PostgreSQL, RLS on every table |
| Compute | Modal serverless containers, CPU-only (`libx264`) |
| Transcription | Groq `whisper-large-v3-turbo` |
| Selection + SEO | DeepSeek |
| Storage | Cloudflare R2 + Modal Volume fallback |
| Frontend | Vanilla JS PWA |

Render is **CPU-bound by design, not GPU** — the whole point of choosing
`libx264` over an accelerated encoder is that a 60-minute source can be turned
into a full set of clips for a few cents.

## How a job runs

```
Mobile PWA  ──POST /api/jobs──►  FastAPI  ──enqueue──►  Modal worker
                                                              │
                          ┌───────────────────────────────────┤
                          │ 1. fetch source (yt-dlp / Drive / Frame.io)
                          │ 2. transcribe            (Groq Whisper)
                          │ 3. probe audio + visual signals (FFmpeg)
                          │ 4. select hooks + score virality (DeepSeek)
                          │ 5. render 9:16 + captions (FFmpeg, face-tracked crop)
                          └───────────────────────────────────┘
                                    │
                          SSE progress ──► PWA  ──► publish kit
```

## Layout

```
app/
  api/          FastAPI routes (jobs, clips, templates, payments, share, push)
  pipeline/     transcriber, intelligence, orchestrator, video_editor, face_track
  auth.py       Supabase JWT gate; the backend uses the anon key and is itself
                subject to RLS rather than holding a service-role key
  database.py   engine + models
  config.py     env config, plan tiers, quota clamps
  dodo.py       Dodo Payments, webhook signature verification
modal_app.py    the serverless pipeline
public/         the PWA shell and client JS
assets/         template folders (gaming_neon, brand_bold, retro_vhs, ...)
scripts/        content pack and release tooling
supabase/migrations/   schema, RLS, credit ledger
tests/          pytest suite
```

## Running it

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests -q          # 71 passed, 1 skipped — no DB, keys or GPU needed
ruff check app scripts modal_app.py dev_server.py
```

The suite runs against an in-memory SQLite fixture and mocks Groq, DeepSeek,
ffmpeg and Modal, so it is fast and hermetic.

Running the full stack needs a Supabase project and a Modal account. Every
environment variable is declared in `app/config.py`, which reads them from
`.env` (see `model_config` at the bottom of that file). There is no committed
`.env.example`, so read `app/config.py` or `_update_secrets.py` for the shape.

## Status

Working: the full pipeline — link/file ingest, transcription, hook selection,
face-tracked vertical reframing, animated captions, templates, SSE progress,
mobile job history, share links, push subscriptions, credit ledger.

Billing exists but is **inert**: `dodo_test_mode` defaults to `True` and the
product IDs are blank, so nothing charges until they are filled in deliberately.

Known gaps:

- Cloudflare R2 is wired but currently disabled; Modal Volume is the working path
- 4K is not supported — encode height is clamped to 1080p
- Clip quality still needs human review. Third-party testing across this category
  finds 20–40% of machine-selected clips get discarded, and virality scores
  correlate weakly with real performance.
- `add_tiers_credits.sql` creates `user_tiers` / `monthly_usage`, which are *not*
  the live tables — those are `usertier` / `monthlyusage`, created by SQLModel's
  `create_all`. `fix_credit_tables.sql` documents this. It is stale and would
  create empty wrongly-named tables on a fresh database.

## Security notes

- RLS is enabled on `job`, `videoclip`, `pushsubscription`, `payment`,
  `usertier`, `quotausage` and `monthlyusage`. `pushsubscription` is
  deliberately deny-all with no policy.
- The Supabase **anon** key is committed in `public/auth.js` because it is
  designed to ship in client code. Safety therefore depends entirely on the RLS
  policies above. There is no service-role key in the repository.
- Dodo webhooks are signature-verified with `standardwebhooks` and are
  idempotent. Unknown event types are acknowledged and ignored.
- Credits are deducted in the same transaction as job creation, so a balance
  cannot be double-spent under concurrency.

## Licence

No licence file is present, so default copyright applies. The code is publicly
readable, but nobody may copy, fork or redistribute it until one is added.

## Documentation

| File | |
|---|---|
| [`prd.md`](prd.md) | Product requirements v4.0 |
| [`PLAN.md`](PLAN.md) | Build plan and current state |
| [`PIPELINE_ANALYSIS.md`](PIPELINE_ANALYSIS.md) | Pipeline behaviour and edge cases |