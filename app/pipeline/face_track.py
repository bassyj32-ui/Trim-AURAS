"""Face-aware crop — speaker tracking for Opus-style animated crops.

The pipeline detects faces ONCE per job, records a normalized face track
(list of ``{"t", "cx", "cy"}`` where ``t`` is absolute source-video time in
seconds and ``cx``/``cy`` are the face-center in normalized 0..1
coordinates), and stores it on the Job. Every render (pipeline,
generate-more, trim) then animates the cover-crop so the speaker stays in
frame — the classic "auto-face-track" short-cut look.

Detection order:
  1. MediaPipe face detection — only used when the package is importable
     (it is NOT a hard dependency; Modal's Python 3.13 image doesn't carry
     it, so in practice the OpenCV path runs).
  2. OpenCV Haar cascade (``haarcascade_frontalface_default.xml``, bundled
     with opencv) — dependable, zero model downloads.

Returns ``[]`` when no faces are found so renders can fall back to the
static center crop. Never raises: any detection failure degrades to ``[]``
and the pipeline continues with static crops.
"""

import logging

log = logging.getLogger(__name__)


def detect_face_track(
    video_path: str,
    sample_interval: float = 0.5,
    max_width: int = 480,
) -> list[dict]:
    """Return a smoothed normalized face track for the whole source video.

    ``sample_interval`` is the time (seconds) between detection frames;
    detection runs on downscaled frames (``max_width`` px wide) so the scan
    is fast enough for background pipeline use. Coordinates are normalized
    to the ORIGINAL frame: ``cx = face_center_x / width``.
    """
    track = _detect_mediapipe(video_path, sample_interval)
    if track:
        log.info(f"[face_track] mediapipe: {len(track)} samples")
        return _smooth_track(track)
    track = _detect_opencv(video_path, sample_interval, max_width)
    if track:
        log.info(f"[face_track] opencv: {len(track)} samples")
        return _smooth_track(track)
    log.info("[face_track] no faces found — static center crop will be used")
    return []


def _detect_mediapipe(video_path: str, sample_interval: float) -> list[dict] | None:
    """MediaPipe face detection — returns None when mediapipe is unavailable."""
    try:
        import cv2
        import mediapipe as mp
    except Exception:
        return None

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if fps <= 0:
            cap.release()
            return None
        step = max(int(round(sample_interval * fps)), 1)
        track: list[dict] = []
        with mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        ) as detector:
            idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % step != 0:
                    idx += 1
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = detector.process(rgb)
                best = None
                best_score = -1.0
                for d in res.detections or []:
                    score = d.score[0] if d.score else 0.0
                    if score > best_score:
                        best = d.location_data.relative_bounding_box
                        best_score = score
                if best is not None:
                    cx = best.xmin + best.width / 2.0
                    cy = best.ymin + best.height / 2.0
                    track.append(
                        {"t": idx / fps, "cx": max(0.0, min(1.0, cx)), "cy": max(0.0, min(1.0, cy))}
                    )
                idx += 1
        cap.release()
        return track or None
    except Exception as e:
        log.warning(f"[face_track] mediapipe detection failed (non-fatal): {e}")
        try:
            cap.release()
        except Exception:
            pass
        return None


def _detect_opencv(
    video_path: str,
    sample_interval: float,
    max_width: int,
) -> list[dict]:
    """OpenCV Haar detection on downscaled frames — the dependable path."""
    import cv2

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if fps <= 0 or width <= 0 or height <= 0:
            cap.release()
            return []

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            cap.release()
            log.warning("[face_track] Haar cascade failed to load")
            return []

        scale = min(max_width / width, 1.0)
        dw = max(int(width * scale), 1)
        dh = max(int(height * scale), 1)
        step = max(int(round(sample_interval * fps)), 1)

        track: list[dict] = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step != 0:
                idx += 1
                continue
            small = cv2.resize(frame, (dw, dh)) if scale < 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
            )
            if len(faces) > 0:
                # Keep the largest face (the speaker / closest subject)
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w / 2.0) / dw
                cy = (y + h / 2.0) / dh
                track.append(
                    {"t": idx / fps, "cx": max(0.0, min(1.0, cx)), "cy": max(0.0, min(1.0, cy))}
                )
            idx += 1
        cap.release()
        return track
    except Exception as e:
        log.warning(f"[face_track] opencv detection failed (non-fatal): {e}")
        try:
            cap.release()
        except Exception:
            pass
        return []


def _smooth_track(track: list[dict], window: int = 5) -> list[dict]:
    """Median-filter the cx/cy series to remove single-frame jitter.

    Keeps timestamps untouched; only the coordinates are smoothed. A median
    window also rejects brief misdetections (one bad sample can't yank the
    crop). Lists shorter than the window pass through unchanged.
    """
    import statistics

    if len(track) < 3:
        return track
    n = len(track)
    half = window // 2
    out: list[dict] = []
    for i, s in enumerate(track):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        cxs = [track[j]["cx"] for j in range(lo, hi)]
        cys = [track[j]["cy"] for j in range(lo, hi)]
        out.append(
            {
                "t": s["t"],
                "cx": statistics.median(cxs),
                "cy": statistics.median(cys),
            }
        )
    return out
