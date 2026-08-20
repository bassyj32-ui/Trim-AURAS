# TrimAURA Core Pipeline — Analysis

> **Verification note (2026-08-19):** this analysis was checked against the
> codebase. ~95% accurate. Two corrections:
> 1. **Face-track detection order is reversed in the original draft** —
>    the code tries **MediaPipe first**, then falls back to **OpenCV Haar**
>    (`app/pipeline/face_track.py:39-41`), not the other way around.
> 2. DeepSeek model used is `deepseek-v4-flash`, `temperature 0.4`
>    (`app/pipeline/intelligence.py:60-65`).
>
> Everything else verified: classify thresholds (speech_ratio ≥ 0.15,
> cuts_per_min ≥ 6), 300s DeepSeek timeout, signal extraction
> (`select=gt(scene,0.3)`, RMS 85th percentile, `blackdetect=d=0.5`),
> word-level silence trim (0.5s gaps, ≥1.2s floor, `atrim/asetpts/concat`),
> ASS karaoke `\k` tags + mandatory PlayResX/PlayResY, 6 templates at
> 1080×1920@30fps, face-track (0.5s @ 480px, median window 5, 180-sample
> cap, static-crop fallback), keyword scoring (title ×3, transcript ×1) +
> content affinity, Groq `whisper-large-v3-turbo` with segments→words
> fallback, yt-dlp + Frame.io GraphQL + cookies, and the hard truth that a
> DeepSeek failure kills the job at ANALYZING (no signal-clip fallback in
> the speech path).
>
> **Verification note 2 (2026-08-20):** the companion code-level deep dive
> (Part 2 below) was also checked against the codebase — ~97% accurate.
> Corrections:
> 1. The "Groq 1.6.0" version label for the `segments=null` regression is
>    not verifiable from the code — the transcriber only documents that
>    `whisper-large-v3-turbo` now returns `segments: null` with flat words.
> 2. The loud-window algorithm does **not** merge sub-threshold gaps — it
>    groups only *consecutive* 0.5s windows above the 85th-percentile RMS
>    threshold.
>
> Version numbers in Part 2's failure table (7.43/7.47/7.48) are
> deployment-history references; every listed mitigation is confirmed in code.

---

## **Deep Dive: The Reality of TrimAURA's Core Pipeline**

### **The Pipeline Flow (End-to-End)**

```
SOURCE URL/FILE
       │
       ▼
┌─────────────────────────────────────┐
│ 1. DOWNLOADER (yt-dlp + Frame.io)   │ ← Gets the raw video
│    - Handles: YouTube, TikTok, IG,  │
│      GDrive, Frame.io, direct MP4   │
│    - Caps resolution (preferred_h)  │
│    - Cookies for auth-walled sources│
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ 2. TRANSCRIBER (Groq Whisper V3)    │ ← Speech → Text + Word Timestamps
│    - whisper-large-v3-turbo         │
│    - word-level timestamps (karaoke)│
│    - Falls back: segments→words     │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ 3. INTELLIGENCE (DeepSeek + FFmpeg) │ ← THE BRAIN
│    a) FFmpeg "Sight" Signals:       │     - Scene cuts (visual boundaries)
│       - scene_times                 │     - Loud windows (energy peaks)
│       - loud_windows                │     - Black ranges (dead air)
│       - black_ranges                │
│    b) classify_content()            │     - speech / action / music
│    c) DeepSeek clip selection       │     - Transcript-driven (speech)
│       OR select_signal_clips()      │     - Signal-driven (no speech)
│    d) snap_clips_to_signals()       │     - HARD RULES: snap to scenes,
│       (post-pass)                   │           avoid black, min 15s
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ 4. VIDEO_EDITOR (FFmpeg)            │ ← THE RENDERER
│    - Template JSON (canvas, slot,   │
│      overlay, color_grade, Ken Burns)│
│    - Face-aware animated crop       │     (Opus-style speaker tracking)
│    - Silence trimming (word gaps)   │     (karaoke-safe)
│    - ASS karaoke captions           │     (word-by-word highlight)
│    - PNG overlay compositing        │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ 5. SEO GENERATOR (DeepSeek)         │ ← THE PACKAGING
│    - 3 title variants               │
│    - Description + hashtags         │
└─────────────────────────────────────┘
       │
       ▼
CLIPS + METADATA → DB → VOLUME/R2 → USER
```

---

### **What Actually Makes "Best Videos" (The Value Chain)**

| Stage | What It Contributes | Reality Check |
|-------|---------------------|---------------|
| **Downloader** | Source quality, format | **Commodity** — yt-dlp does the work. Your edge: Frame.io GraphQL, cookies support |
| **Transcriber** | Accurate words + timing | **Commodity** — Groq Whisper is fast/cheap. Your edge: word timestamps for karaoke |
| **Intelligence** | **CLIP SELECTION** | **THIS IS THE PRODUCT** — DeepSeek + signals = viral prediction |
| **Video Editor** | Visual polish, format | **DIFFERENTIATOR** — Templates, face-track, karaoke, silence-trim = "Opus look" |
| **SEO Generator** | Packaging for platforms | **COMMODITY** — Prompt engineering. Anyone can copy. |

**The moat is stages 3 + 4 working together.**

---

### **Stage 3 Deep Dive: Intelligence (The Brain)**

#### **Content Classification (Lines 287-316, intelligence.py)**
```python
speech_ratio = speech_seconds / video_duration
cuts_per_min = scene_cuts / (duration/60)

if speech_ratio >= 0.15:     → "speech" (podcast, talking head)
elif cuts_per_min >= 6:      → "action" (gameplay, visual demo)
else:                         → "music" (music video, B-roll)
```

**Reality**: This heuristic works but is crude. A 10-min video with 90s of speech = "speech" even if 80% is silence. A fast-talking gaming video with few cuts = "music."

#### **Two Selection Paths**

**Path A: Speech Content (DeepSeek)**
- Sends full transcript + signals + campaign rules to DeepSeek
- DeepSeek returns clips with scores
- **Risk**: DeepSeek hallucinates timestamps, ignores signals, picks generic moments
- **Guard**: `snap_clips_to_signals()` post-pass forces alignment to scene cuts, avoids black ranges

**Path B: No Speech (select_signal_clips)**
1. Longest loud windows → clips
2. Longest scene chunks → clips
3. Even spacing → clips
- **Deterministic** — no AI variance
- **Limitation**: "Generate more" exhausts signals fast

#### **Signal Extraction (FFmpeg "Sight")**
| Signal | Method | Cost | Reliability |
|--------|--------|------|-------------|
| Scene cuts | `select=gt(scene,0.3)` | ~30s/video | Good for hard cuts, misses subtle |
| Loud windows | RMS 85th percentile | ~20s/video | Good for energy, noisy on music |
| Black ranges | `blackdetect=d=0.5` | ~15s/video | Good for dead air |

**Reality**: These run sequentially on CPU. 60-90s total per video. They're "cheap sight" — not vision AI.

---

### **Stage 4 Deep Dive: Video Editor (The Renderer)**

#### **Template System (assets/templates/*/template.json)**
Each template defines:
- **Canvas**: 1080×1920 @ 30fps (fixed)
- **Video slot**: fit_mode (cover/contain), position, size
- **Overlay PNG**: Template frame (scanlines, neon glow, gold frame, etc.)
- **Color grade**: brightness/contrast/saturation/gamma (FFmpeg `eq` filter)
- **Ken Burns**: Subtle zoompan (1.0→1.05 over clip)
- **Subtitles**: Font, size, colors, alignment, margin_v, outline

**6 Templates = 6 Visual Languages** — this is your visual moat.

#### **Face-Aware Crop (face_track.py → video_editor.py)**
1. **Detection**: MediaPipe face detection first, OpenCV Haar cascade fallback, every 0.5s on 480px downscaled
2. **Track**: Normalized `cx, cy` per timestamp, median-smoothed (window=5)
3. **Render**: Scale source 15% larger than canvas, animate `crop=x(t):y(t)` via piecewise-linear FFmpeg expression
4. **Fallback**: Static center crop if <2 face samples

**Reality**:
- Works well for talking heads (single speaker, centered)
- Fails on: multi-person, fast movement, side-profile, hands in face
- Expression size capped at 180 samples (Windows cmd limit)

#### **Silence Trimming (video_editor.py:189-260)**
- Uses Whisper **word timestamps** (not segment)
- Cuts gaps ≥0.5s between words + leading/trailing dead air
- **Critical**: Cuts ONLY between words → karaoke `\k` durations stay frame-accurate
- Audio condensed with same keep-intervals (`atrim/asetpts/concat`)
- Safety floor: keeps ≥1.2s

**Reality**: This is **the Opus killer feature**. Most tools cut at segment level (breaks captions). You cut at word level (preserves karaoke).

#### **Karaoke Captions (video_editor.py:263-417)**
- ASS format with `\k` tags per word (centiseconds)
- Secondary color = highlight color (flips white→accent as spoken)
- Emoji injection per keyword (90+ mappings)
- PlayResX/PlayResY **mandatory** (fixes libass 384×288 default canvas bug)
- Falls back to plain text if no word timestamps

**Reality**: This is **production-grade**. The PlayRes fix (7.48) was the blocker — now solved.

---

### **Where the Pipeline Succeeds vs Struggles**

| Input Type | Success Rate | Why |
|------------|--------------|-----|
| **Podcast/Talking Head** | ★★★★★ | Speech → DeepSeek picks hooks → face-track centers speaker → karaoke captions = Opus clone |
| **Gaming/Commentary** | ★★★★☆ | Speech + action signals → gaming_neon template → face-track works if facecam |
| **Music Video** | ★★★☆☆ | No speech → signal clips (loud/scenes) → generic SEO (title only) → mrbeast/retro template |
| **Gameplay No Commentary** | ★★★☆☆ | Action classification → scene-based clips → no captions → relies on template visual |
| **Vlog/Handheld** | ★★★☆☆ | Face-track unstable (movement) → static crop fallback → still works |
| **Screen Recording** | ★★☆☆☆ | No face, no speech often → signal clips → blurpad template = boring |
| **Interview (2+ people)** | ★★☆☆☆ | Face-track picks largest face → jumps between speakers → distracting crop |

---

### **The Hard Truths**

#### **1. DeepSeek is the Bottleneck**
- 300s timeout needed (Modal load = 30-90s per call)
- Cost: ~$0.03/clip for analysis + SEO
- **No fallback** if DeepSeek fails → job dies at ANALYZING
- Prompt is generic — no few-shot examples, no chain-of-thought

#### **2. Template Selection is Heuristic, Not Learned**
- `recommend_template()` = keyword scoring + content affinity
- No feedback loop: viral_score never feeds back into template choice
- "Auto" picks once at render; generate-more reuses same template

#### **3. Face-Track is Binary (Works or Doesn't)**
- No confidence scoring — either track exists or static fallback
- No manual override in UI (user can't say "track this person")

#### **4. Silence Trim + Karaoke = The Real Differentiator**
- **This is what Opus does** — and you have it working
- Word-level cuts + word-level captions = retention optimizer
- Most competitors: segment-level cuts + static captions

#### **5. No Visual Understanding**
- FFmpeg signals = proxy for "sight"
- No: object detection, text-on-screen OCR, brand logo detection, emotion recognition
- DeepSeek only sees transcript — **blind to visual context**

---

### **What "Best Videos" Actually Requires (Missing Pieces)**

| Capability | Current | Needed for "Best" |
|------------|---------|-------------------|
| **Hook detection** | DeepSeek guesses | First 3s analysis (visual + audio) |
| **Retention prediction** | Viral score (0-100) | Per-second retention curve estimate |
| **Visual variety** | Template overlay only | B-roll insertion, zoom punch-ins, text overlays |
| **Platform optimization** | Same render everywhere | TikTok: faster pace, IG: aesthetic, YT: longer |
| **Speaker diarization** | Single face track | Multi-speaker tracking + lower-third names |
| **Brand consistency** | Template only | Logo, colors, fonts per user (brand kit) |
| **A/B testing** | None | Generate variants, test, learn |

---

### **The Real Product Strategy**

**Don't chase "smarter AI."** Chase **reliable execution of the basics:**

1. **Never fail on speech content** → DeepSeek retry + fallback to signal clips
2. **Every clip has karaoke captions** → Whisper word timestamps are non-negotiable
3. **Face-track works 90%+ on talking heads** → Improve detection, add manual fallback
4. **Templates are visually distinct** → 6 is good; make previews *actually show the difference*
5. **Silence trim is on by default** → It's the retention hack; make it the happy path
6. **Clip viewer page sells the clip** → Poster + 3 titles + platform buttons = shareable asset

---

### **Immediate Improvements (No New Tech, Just Polish)**

| Fix | Effort | Impact |
|-----|--------|--------|
| **DeepSeek few-shot examples** in prompt | 1 hr | Better clip selection, fewer hallucinated timestamps |
| **Viral score → template feedback** | 2 hrs | Learn which templates score higher per genre |
| **Face-track confidence + UI override** | 1 day | Fix the "wrong person tracked" problem |
| **Per-platform render variants** | 1 week | TikTok 30s fast, IG 60s aesthetic, YT 90s deep |
| **Brand kit (logo/colors/fonts)** | 1 week | Lock in agencies/creators |
| **Hook analyzer (first 3s)** | 1 week | Data-driven clip start optimization |

---

### **Bottom Line**

**Your pipeline makes "best videos" when:**
- Input has **clear speech** (podcast, commentary, interview)
- **Single speaker** (face-track works)
- **Viral moments exist in transcript** (DeepSeek finds them)
- **Template matches content** (gaming→neon, business→bold)

**It produces "generic clips" when:**
- No speech (music, pure gameplay)
- Multi-speaker / moving camera
- DeepSeek picks weak moments
- Template mismatch

**The 80/20**: Fix DeepSeek reliability + silence trim default + template previews + clip viewer page. That's 80% of "Opus quality" with 20% of the effort.

---

# Part 2 — Complete Technical Deep Dive: All 5 Pipeline Stages

> Code-level companion to Part 1. Verified against the source on 2026-08-20
> (see verification note 2 at the top for the two corrections applied below).

## **STAGE 1: DOWNLOADER** (`app/pipeline/downloader.py`)

### **Entry Point**

```python
execute_download(source: str, cookies_file: str | None = None, preferred_height: int = 1080) -> str
```

Returns absolute path to downloaded/copied video file.

### **Source Type Detection (Priority Order)**

| Check              | Function            | Handles                                                 |
| :----------------- | :------------------ | :------------------------------------------------------ |
| 1. Local file      | `_is_local_path()`  | Uploaded files (`/mnt/data/uploads/...`)                |
| 2. Frame.io        | `_is_frameio()`     | `frame.io`, `share.frame.io`, `next.frame.io`           |
| 3. Direct file     | `_is_direct_file()` | `.mp4`, `.mov`, `.mkv`, `.webm`, `.m4a`, `.mp3`, `.wav` |
| 4. YouTube         | `_is_youtube()`     | **BLOCKED** — raises `ValueError`                       |
| 5. Everything else | yt-dlp              | TikTok, Instagram, Google Drive, Twitter/X, Vimeo, etc. |

### **Frame.io GraphQL Download (Unique Feature)**

**Two GraphQL Queries:**

```graphql
# 1. List assets in share
query GetShareAssets($shareId: ID!) {
  share(shareId: $shareId) {
    collectionAssets(assetType: FILE, page: {first: 200}) {
      nodes { id }
    }
  }
}

# 2. Get asset details + transcodes
query GetAssetsForViewer($assetIds: [ID!]!) @stewardship(stewards: [VIEWER]) {
  assets(assetIds: $assetIds) {
    id name assetType
    ... on VideoAsset {
      media {
        id duration filesize
        metadata { originalHeight originalWidth }
        original { downloadUrl filesizeInBytes }
        videoTranscodes { key downloadUrl filesizeInBytes height width codec }
      }
    }
  }
}
```

**Auth Header**: `x-frameio-share-authentication: base64(share_id)` — no account needed.

**Quality Selection** (`_pick_transcode`):

- Iterates from `preferred_height` down to 1
- Picks highest transcode ≤ preferred height
- Falls back to the highest transcode (then the original) if none matches

**SSRF-Safe Streaming** (`_stream_download`):

- Walks redirects **one hop at a time**
- Validates **each hop** with `validate_source_url()` (blocks 169.254.x.x, 10.x.x.x, etc.)
- 10-hop hard limit

### **yt-dlp Configuration** (`_get_ydl_opts`)

```python
{
    "format": "best[height<=1080]/best",  # caps resolution
    "extractor_args": {
        "youtube": {"player_client": ["default"]}  # tv_embedded works 2026
    },
    "user_agent": "Chrome 120...",
    "impersonate": ImpersonateTarget.from_str("chrome"),  # curl_cffi TLS fingerprint
    "cookiefile": "/mnt/data/cookies/{job_id}.txt"  # if provided
}
```

**PO-Token Provider** (`_ensure_pot_server`):

- Starts `bgutil-pot` binary on `localhost:4416`
- yt-dlp plugin `bgutil-ytdlp-pot-provider` auto-connects
- Mints Proof-of-Origin tokens for YouTube bot bypass
- **Reality**: Still fails on Modal IPs (Google blocks datacenter ranges) — hence the YouTube block

### **Error Modes**

| Error                                          | Cause                                |
| :--------------------------------------------- | :----------------------------------- |
| `ValueError: YouTube is disabled`              | YouTube URL detected                 |
| `RuntimeError: Download completed but no file` | yt-dlp succeeded but workspace empty |
| `RuntimeError: SSRF check failed`              | Redirect to private IP               |
| `RuntimeError: Too many redirects`             | >10 redirect hops                    |

---

## **STAGE 2: TRANSCRIBER** (`app/pipeline/transcriber.py`)

### **Entry Point**

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_transcribe(video_path: str) -> list[dict[str, Any]]
```

### **Audio Extraction** (`_extract_audio`)

```bash
ffmpeg -i {video} -vn -acodec libmp3lame -ar 16000 -ac 1 -y {temp}.mp3
```

- Strips video, mono 16kHz MP3 (Whisper optimal)
- `check=True` → raises on ffmpeg failure

### **Groq API Call**

```python
client.audio.transcriptions.create(
    file=(filename, file_handle),
    model="whisper-large-v3-turbo",
    response_format="verbose_json",
    language="en",
    timestamp_granularities=["word"]  # CRITICAL for karaoke
)
```

**Cost**: ~$0.04/hour of audio (estimate)

### **Response Handling — Two Shapes**

**Shape A: Normal (segments + words)**

```json
{
  "segments": [
    {"start": 1.2, "end": 4.5, "text": "Hello world", "words": [{"word": "Hello", "start": 1.2, "end": 1.5}, ...]}
  ],
  "words": [...]  // flat array
}
```

**Shape B: Groq Regression (segments=null, words populated)** — version label in the original draft ("1.6.0") is not verifiable; the code just documents `whisper-large-v3-turbo` returning `segments: null` with flat words.

```json
{
  "segments": null,
  "words": [{"word": "Hello", "start": 1.2, "end": 1.5}, ...]
}
```

**Fallback Logic** (lines 43-50):

```python
if not segments:
    words = [_normalize_word(w) for w in (response.words or [])]
    segments = _segments_from_words(words)
```

### **Segment Reconstruction** (`_segments_from_words`)

**Rules:**

- Split on pause > **2.5 seconds** OR **20 words** max
- Honors sentence-ending punctuation (`.`, `!`, `?`)
- Each segment gets: `start`, `end`, `text`, `words[]`

```python
for w in words:
    if cur and (w["start"] - cur[-1]["end"] > 2.5 or len(cur) >= 20):
        flush()
    cur.append(w)
```

### **Word Attachment** (`_words_for_segment`)

Handles **both** response shapes:

1. **Nested**: `seg["words"]` exists → use those
2. **Flat**: Filter `response.words` by `seg_start <= word.start < seg_end`

### **Output Schema**

```python
[
    {
        "start": 1.2,           # float, seconds
        "end": 4.5,
        "text": "Hello world",
        "words": [
            {"word": "Hello", "start": 1.2, "end": 1.5},
            {"word": "world", "start": 1.6, "end": 1.9}
        ]
    },
    ...
]
```

### **Failure Modes**

| Error                      | Cause             | Mitigation                          |
| :------------------------- | :---------------- | :---------------------------------- |
| Groq 429/timeout           | Rate limit / load | Tenacity retry (3×, 10-40s backoff) |
| `segments: null`           | Groq API change   | Fallback reconstruction ✓           |
| ffmpeg audio extract fails | Corrupt video     | `check=True` raises → job FAILED    |
| Empty segments             | Silent video      | Returns `[]` → intelligence handles |

---

## **STAGE 3: INTELLIGENCE** (`app/pipeline/intelligence.py`)

### **Entry Point**

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_analyze(
    segments: list[dict],
    max_clips: int = 5,
    existing_clips: list[dict] | None = None,
    campaign_rules: str = "",
    video_signals: dict | None = None,
) -> list[dict]
```

### **Step 1: FFmpeg "Sight" Signals** (`extract_video_signals`)

**Four Probes Run Sequentially:**

| Signal           | FFmpeg Command                                                          | Output                                | Time  |
| :--------------- | :---------------------------------------------------------------------- | :------------------------------------ | :---- |
| **Duration**     | `ffprobe -show_entries format=duration`                                 | float seconds                         | ~2s   |
| **Scene cuts**   | `ffmpeg -vf "scale=-1:360,select=gt(scene,0.3),showinfo" -an -f null -` | `[pts_time:12.3, pts_time:45.1, ...]` | ~30s  |
| **Black ranges** | `ffmpeg -vf "scale=-1:360,blackdetect=d=0.5:pix_th=0.1" -an -f null -`  | `black_start:10.2 black_end:12.5`     | ~20s  |
| **Loud windows** | `ffmpeg -ac 1 -ar 8000 -f f32le -` → Python RMS calc                    | `[(5.1, 8.3), (42.0, 48.2), ...]`     | ~25s  |

**Total: ~77s per video** (CPU-bound, runs in `asyncio.to_thread`)

**Loud Window Algorithm:**

1. Decode audio to 8kHz mono f32le (raw PCM)
2. RMS per 0.5s window (8000 samples × 4 bytes)
3. Threshold = 85th percentile of all RMS values
4. Group **consecutive** windows above threshold (no gap bridging — corrected)

### **Step 2: Content Classification** (`classify_content`)

```python
speech_ratio = total_speech_seconds / video_duration
cuts_per_min = len(scene_times) / (duration / 60)

if speech_ratio >= 0.15:     return "speech"
elif cuts_per_min >= 6:      return "action"
else:                         return "music"
```

**Thresholds:**

- **Speech**: ≥15% of video has transcript coverage
- **Action**: ≥6 scene cuts/minute (fast-paced visual)
- **Music**: Neither (music videos, B-roll, ambient)

### **Step 3: Clip Selection — Two Paths**

#### **Path A: Speech Content → DeepSeek** (`execute_analyze`)

**Prompt Construction:**

```
SYSTEM: [clip_analysis.txt prompt with {max_clips} substituted]
USER:
TRANSCRIPT:
[0.0-5.2] Hello everyone welcome to...
[5.2-12.1] Today we're talking about...

CAMPAIGN RULES:
Focus on AI tools, avoid politics

VIDEO SIGNALS:
HIGH-ENERGY WINDOWS: 12.3-18.7, 45.2-52.1
SCENE BOUNDARIES: 10.1, 25.4, 40.2
BLACK/DEAD-AIR RANGES: 3.2-4.1, 20.0-21.5

Previously selected clips (DO NOT repeat):
  - Already used: [12.3-18.7] (High energy opener)

Return JSON array of clips.
```

**API Call:**

```python
payload = {
    "model": "deepseek-v4-flash",
    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
    "temperature": 0.4,
}
async with AsyncClient(timeout=300) as client:  # 5 MINUTE TIMEOUT
    resp = await client.post("https://api.deepseek.com/v1/chat/completions", ...)
```

**Response Parsing:**

```python
raw = resp.json()["choices"][0]["message"]["content"]
raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
clips = json.loads(raw)
```

**Score Normalization:**

```python
for c in clips:
    score = c.get("score")
    if score is not None:
        c["score"] = max(0, min(100, int(round(float(score)))))
clips.sort(key=lambda c: c["score"] if c["score"] is not None else -1, reverse=True)
```

#### **Path B: No Speech → Signal Clips** (`select_signal_clips`)

**Deterministic Priority:**

1. **Loud windows** (longest first) — energy peaks
2. **Longest scene chunks** — uninterrupted visual segments
3. **Even spacing** — fallback across duration

**Overlap Prevention:**

```python
def overlaps(s, e):
    return any(s < x["end"] and e > x["start"] for x in existing_clips + clips)
```

**Minimum Clip**: 15 seconds (configurable)

### **Step 4: Snap to Signals** (`snap_clips_to_signals`)

**Hard Post-Pass Rules (applies to BOTH paths):**

| Rule                            | Implementation                                             |
| :------------------------------ | :--------------------------------------------------------- |
| Snap start to nearest scene cut | `min(scene_times, key=lambda s: abs(s - start))` within 2s |
| Snap end to nearest scene cut   | Same, must be > start                                      |
| Push start OUT of black range   | If `bs < start < be` → `start = be`                        |
| Pull end BACK from black range  | If `bs < end < be` → `end = bs`                            |
| Drop clip entirely in black     | If `start >= bs and end <= be` → discard                   |
| Enforce minimum duration        | Drop if `end - start < 15s`                                |

**Guarantee**: Never returns empty — falls back to original clips if all dropped.

### **Step 5: Template Recommendation** (`recommend_template`)

**Scoring:**

- Title keyword hit: **3 points**
- Transcript keyword hit: **1 point**
- Content affinity bonus (speech→podcast\_split, action→gaming\_neon, music→mrbeast)

**Genres per Template** (from `template.json`):

```json
"genres": ["gaming", "gameplay", "esports", "minecraft", ...]
```

---

## **STAGE 4: VIDEO EDITOR** (`app/pipeline/video_editor.py`)

### **Entry Point**

```python
async def execute_render(
    video_path: str,
    clips: list[dict],
    segments: list[dict],
    template_id: str,
    burn_text: bool = False,
    apply_overlay: bool = True,
    trim_silence: bool = False,
    face_track: list[dict] | None = None,
) -> list[str]  # output paths
```

### **Template Loading** (`_load_template`)

```json
{
  "id": "gaming_neon_v1",
  "canvas": {"width": 1080, "height": 1920, "fps": 30},
  "video_slot": {"width": 1080, "height": 1920, "x_offset": 0, "y_offset": 0, "fit_mode": "cover"},
  "overlay_image": "overlay.png",
  "color_grade": {"brightness": 0.0, "contrast": 1.15, "saturation": 1.4, "gamma": 1.0},
  "ken_burns": {"enabled": true, "zoom_start": 1.0, "zoom_end": 1.05},
  "subtitles": {"alignment": 2, "margin_v": 180, "font_name": "Impact", "font_size": 32, "primary_color": "&H0000FFFF", "highlight_color": "&H00FF00FF", "outline_color": "&H00000000", "outline_width": 4}
}
```

### **Per-Clip Render Loop**

#### **1. Silence Cuts** (`_compute_silence_cuts`)

**Input**: Whisper word timestamps (not segments!)

```python
words = [(word_start, word_end) for seg in segments for word in seg.get("words", [])]
```

**Algorithm:**

- Gap ≥ 0.5s between consecutive words → cut
- Leading dead air (first\_word\_start - clip\_start ≥ 0.5s) → cut
- Trailing dead air (clip\_end - last\_word\_end ≥ 0.5s) → cut
- **Safety**: If kept duration < 1.2s → no cuts

**Output**: `[(cut_start, cut_end), ...]` in **absolute source time**

#### **2. Keep Intervals** (`_keep_intervals`)

Inverts cuts → intervals to KEEP (for `concat` filter)

#### **3. Time Remapping** (`_shift_time`)

Maps clip-relative time → silence-condensed timeline

- Only affects timeline BETWEEN words
- Karaoke `\k` durations **unchanged**

#### **4. Face-Aware Crop** (`_build_animated_crop`)

**Input**: Normalized face track `[{"t": 12.3, "cx": 0.52, "cy": 0.48}, ...]`

**Process:**

1. Filter samples within `trim_start - 0.5` to `trim_end + 0.5`
2. Remap times through silence cuts (`_shift_time`)
3. Cap at 180 samples (Windows cmd limit)
4. Scale source to cover canvas + **15% slack**
5. Generate piecewise-linear FFmpeg expressions for `x(t)` and `y(t)`

**Expression Format** (half-open intervals to avoid double-counting):

```
lt(t,t0)*v0 + gte(t,t0)*lt(t,t1)*(v0+slope*(t-t0)) + ... + gte(t,tn)*vn
```

**Fallback**: Returns `None` if <2 samples → static center crop

#### **5. Filter Chain Construction**

**Video Chain (simplified):**

```
[0:v]trim=start:end,setpts=PTS-STARTPTS
  → if silence cuts: split into keep intervals → concat → [condv]
  → scale/crop (face-track or cover/contain)
  → ken_burns zoompan (if enabled)
  → fps=30
  → [main]

[0:v]scale=1080:1920:force_original_aspect_ratio=2,boxblur=5:2 → [bg]  (contain mode only)
[bg][main]overlay=x:y → [withvid]

[1:v]format=rgba → [overlay]  (PNG overlay)
[withvid][overlay]overlay=0:0 → [withovl]

[withovl]eq=brightness:contrast:saturation:gamma → [graded]  (color grade)

[graded]subtitles=subs.ass:charenc=utf-8 → [out]  (if burn_text)
[graded]null → [out]  (if no burn_text)
```

**Audio Chain (if silence cuts + has\_audio):**

```
[0:a]atrim=keep_start:keep_end,asetpts=PTS-STARTPTS → [ka0], [ka1]...
[ka0][ka1]...concat=n=N:v=0:a=1 → [conda]
-map [out] -map [conda]
```

**No Audio Fallback**: Adds `anullsrc` silent track (YouTube rejects no-audio files)

#### **6. ASS Subtitle Generation** (`_build_subtitle_file`)

**Karaoke Mode** (`burn_text=True`):

- Each word → `{\k{dur_cs}}word` (centiseconds)
- `PlayResX: 1080`, `PlayResY: 1920` **MANDATORY** (fixes libass 384×288 default)
- Secondary color = template `highlight_color` (flips as spoken)
- Emoji injection per keyword (90+ mappings)

**Plain Mode** (`burn_text=False`):

- Segment-level text, no `\k` tags
- Still gets emoji injection

**Cut Remapping**: Dialogue times shifted via `_shift_time` so captions stay synced after silence removal.

#### **7. FFmpeg Execution**

```bash
ffmpeg -i source.mp4 -i overlay.png -filter_complex "..." \
  -map "[out]" -map "[conda]" -t {duration} -r 30 \
  -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -preset veryfast -crf 23 \
  -c:a aac -movflags +faststart -y output.mp4
```

**Stderr Streaming**: Line-by-line to `/mnt/data/diag/clip_{n}_{run_id}.stderr.log` + console

**Per-Run ID**: `time_ns() + counter` prevents log clobbering on concurrent renders

---

## **STAGE 5: SEO GENERATOR** (`app/pipeline/seo_generator.py`)

### **Entry Point**

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=10, min=10, max=40))
async def execute_seo(transcript_text: str, campaign_rules: str = "") -> dict
```

### **Prompt** (`prompts/seo_generation.txt`)

```
You are a viral social media headline writer. For the provided short clip transcript, generate exactly 3 title variations and metadata in valid JSON.

SCHEMA:
{
  "title_curiosity": "Curiosity hook under 60 chars (e.g., 'Why 90% of Coders Fail This Test...')",
  "title_direct": "Bold, punchy statement under 60 chars (e.g., 'Stop Using This Framework in 2026.')",
  "title_question": "Engaging question under 60 chars (e.g., 'Is This the End of Traditional Coding?')",
  "description": "Engaging 2-sentence summary with call to action.",
  "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5"
}
```

### **API Call**

```python
payload = {
    "model": "deepseek-v4-flash",
    "messages": [system_prompt, user_msg],
    "temperature": 0.7,
}
async with AsyncClient(timeout=60) as client:
    resp = await client.post("https://api.deepseek.com/v1/chat/completions", ...)
```

### **Input Truncation**

```python
user_msg = f"TRANSCRIPT:\n{transcript_text[:2000]}\n\n"  # Hard cap at 2000 chars
```

### **Output**

```python
{
    "title_curiosity": "...",
    "title_direct": "...",
    "title_question": "...",
    "description": "...",
    "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5"
}
```

---

## **ORCHESTRATOR** (`app/pipeline/orchestrator.py`) — The Glue

### **Full Pipeline** (`execute_pipeline`)

```python
async def execute_pipeline(job_id: int):
    # Phase 1: DOWNLOAD
    video_path = await asyncio.to_thread(execute_download, job.source_url, cookies_file, preferred_height)
    upload_to_r2(video_path, f"sources/{job_id}_source.mp4")  # non-fatal
    _cache_source(job_id, video_path)  # Volume cache for generate-more

    # Phase 2: TRANSCRIBE
    segments = await execute_transcribe(video_path)
    _update_job(job_id, transcript_json=json.dumps(segments))

    # Phase 3: ANALYZE
    video_signals = await asyncio.to_thread(extract_video_signals, video_path)
    face_track = await asyncio.to_thread(detect_face_track, video_path)
    if face_track: _update_job(job_id, face_track_json=json.dumps(face_track))

    has_speech = len(transcript_text) >= 10
    content_type = classify_content(segments, video_signals)

    if has_speech:
        clips = await execute_analyze(segments, max_clips, campaign_rules, video_signals)
    else:
        clips = select_signal_clips(max_clips, video_signals)
    clips = snap_clips_to_signals(clips, video_signals)

    # Phase 4: RENDER
    template_id = job.template_id
    if template_id == "auto":
        template_id = recommend_template(content_type, job.title, transcript_text)
        _update_job(job_id, template_id=template_id)

    rendered_paths = await execute_render(video_path, clips, segments, template_id,
                                          burn_text=job.burn_captions,
                                          trim_silence=job.trim_silence,
                                          face_track=face_track)

    # Phase 5: SEO + UPLOAD (PER CLIP, PROGRESSIVE)
    for i, rendered_path in enumerate(rendered_paths):
        clip_transcript = get_clip_transcript(segments, clips[i]["start"], clips[i]["end"])
        seo_data = await execute_seo(clip_transcript, campaign_rules)

        # Upload to R2 (or skip if disabled)
        r2_url = upload_to_r2(rendered_path, f"clips/{job_id}_{i}.mp4")

        # Save to DB + Volume (progressive commit)
        db_clip = VideoClip(job_id=job_id, ..., r2_url=local_path, r2_key=r2_key)
        session.add(db_clip)
        session.commit()
        await _volume_commit()  # Modal Volume commit for immediate availability

    _update_job(job_id, status=COMPLETED, progress=100)
    _notify_terminal(COMPLETED)  # Push notification
```

> Note: `has_speech` is actually `len(_get_transcript_text(segments).strip()) >= 10` (10+ chars, not a boolean transcript flag). `_cache_source` and the R2 upload both run in Phase 1. Face detection runs only for cover-mode templates (`_template_uses_cover`). The no-speech SEO fallback substitutes the job title.

### **Key Orchestration Features**

| Feature                    | Implementation                                                  |
| :------------------------- | :-------------------------------------------------------------- |
| **Progressive Publishing** | Each clip committed to DB + Volume immediately after render     |
| **Failure Survival**       | Failed job still publishes clips rendered before failure        |
| **Volume Sync**            | `_volume_commit()` after each clip + at end                     |
| **Diagnostics**            | JSONL events per stage (ENTER/EXIT/duration/error)              |
| **Job Payload**            | Full job data passed to Modal worker (bypasses Volume sync lag) |
| **Cookie Persistence**     | `save_job_cookies()` → `/mnt/data/cookies/{job_id}.txt`         |
| **Source Caching**         | `_cache_source()` → `/mnt/data/sources/{job_id}_source.mp4`     |

### **Generate More** (`generate_more_clips`)

- **Skips**: Download + Transcribe
- **Reuses**: `job.transcript_json`, `job.face_track_json`, cached source
- **Excludes**: Existing clip timestamps (passed to DeepSeek)
- **Fallback**: Retries without exclusions if DeepSeek returns nothing

### **Trim Clip** (`trim_clip`)

- **Re-renders single clip** with new boundaries
- **Reuses**: Source, transcript, template, face\_track, burn/trim settings
- **Updates**: Clip row in place (same `clip_id`)
- **Job Status**: Flips to RENDERING → COMPLETED (no push notification)

---

## **DATA FLOW SUMMARY**

```
INPUT                          STAGE 1                    STAGE 2                    STAGE 3                              STAGE 4                              STAGE 5
source_url                 →  execute_download()   →  execute_transcribe()   →  extract_video_signals()         →  execute_render()                  →  execute_seo()
cookies_file                   (video_path)              (segments[])              classify_content()                   (rendered_paths[])                   (seo_data)
preferred_height               (source_r2_key)           (words per segment)       DeepSeek OR signal clips           ASS karaoke + face crop              3 titles
template_id                                                                snap_clips_to_signals()            silence trim + overlay             description
campaign_rules                                                                       template recommendation            color grade + Ken Burns            hashtags
max_clips
burn_captions
trim_silence

OUTPUT                      video_path (local)        segments[]                  clips[]                              rendered_paths[]                     seo_data
                            source_r2_key             transcript_json             video_signals                        clip metadata (start/end/duration)
                            face_track_json                                                                          viral_score (from DeepSeek)
                            (cached on Volume)
```

---

## **COST BREAKDOWN PER JOB (Estimates)**

| Component            | Cost           | Notes                                      |
| :------------------- | :------------- | :----------------------------------------- |
| **Modal Compute**    | $0.10-0.50     | 2 CPU × 5-20 min depending on video length |
| **Groq Whisper**     | $0.02-0.08     | $0.04/hr audio; 10-min video = ~$0.007     |
| **DeepSeek Analyze** | $0.02-0.05     | ~2-5K tokens per call                      |
| **DeepSeek SEO**     | $0.01-0.02     | ~1-2K tokens per clip × 5 clips            |
| **Storage (Volume)** | ~$0.00         | Included in Modal                          |
| **Total/Job**        | **$0.15-0.65** | Scales with video length & clip count      |

---

## **CRITICAL PATH LATENCY**

| Stage               | Typical Time | Bottleneck                          |
| :------------------ | :----------- | :---------------------------------- |
| Download            | 30-120s      | Source bandwidth, yt-dlp extraction |
| Transcribe          | 15-60s       | Groq API latency                    |
| Signals (FFmpeg)    | 60-90s       | **CPU-bound, sequential**           |
| DeepSeek Analyze    | 30-90s       | **API latency (300s timeout)**      |
| Render (per clip)   | 10-40s       | FFmpeg CPU, scales with clip count  |
| SEO (per clip)      | 5-15s        | DeepSeek API                        |
| **Total (5 clips)** | **3-6 min**  | DeepSeek + FFmpeg signals dominate  |

---

## **KNOWN FAILURE POINTS (Production Reality)**

| Stage      | Failure Mode                     | Frequency         | Mitigation                       |
| :--------- | :------------------------------- | :---------------- | :------------------------------- |
| Download   | YouTube bot block                | High (Modal IPs)  | Cookies + PO-token (still flaky) |
| Download   | Frame.io auth expired            | Medium            | Clear error message              |
| Transcribe | Groq `segments: null`            | Fixed in 7.43     | Fallback reconstruction ✓        |
| Transcribe | Groq timeout/429                 | Low               | Tenacity retry                   |
| Analyze    | DeepSeek ReadTimeout             | Medium            | 300s timeout + retry             |
| Analyze    | DeepSeek hallucinates timestamps | Medium            | `snap_clips_to_signals` guard    |
| Render     | FFmpeg hang (apt 5.1.9)          | **Fixed in 7.47** | Pinned ffmpeg 8.1.2 static ✓     |
| Render     | Audio condense EINVAL            | **Fixed in 7.48** | Audio chains before join ✓       |
| Render     | Captions 4× oversized            | **Fixed in 7.48** | PlayResX/PlayResY ✓              |
| SEO        | Empty transcript (music)         | Medium            | Falls back to job title          |

> Version numbers (7.43/7.47/7.48) are deployment-history references; the mitigations are all present in the current code.
