from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from agente_percepcion.detector import Detection


@dataclass(frozen=True)
class TrackingSnapshot:
    track_id: str
    velocidad: float
    permanencia_segundos: int
    movimiento_erratico: bool
    es_nuevo: bool


@dataclass
class _Track:
    track_id: str
    label: str
    box: tuple[int, int, int, int]
    first_seen: float
    last_seen: float
    last_center: tuple[float, float]
    last_velocity: tuple[float, float] = (0.0, 0.0)
    movimiento_erratico: bool = False
    observations: int = 1


@dataclass
class TrackedDetection:
    detection: Detection
    snapshot: TrackingSnapshot


class ObjectTracker:
    def __init__(self, iou_threshold: float = 0.25, max_lost_seconds: float = 10.0) -> None:
        self._iou_threshold = iou_threshold
        self._max_lost_seconds = max_lost_seconds
        self._tracks: dict[str, _Track] = {}
        self._counters: dict[str, int] = {}

    def update(self, detections: list[Detection], now: float) -> list[TrackedDetection]:
        self._prune(now)
        tracked: list[TrackedDetection] = []
        used_track_ids: set[str] = set()

        for detection in detections:
            track = self._match_track(detection, used_track_ids)
            is_new = track is None
            if track is None:
                track = self._new_track(detection, now)
            else:
                self._update_track(track, detection, now)

            used_track_ids.add(track.track_id)
            tracked.append(
                TrackedDetection(
                    detection=detection,
                    snapshot=TrackingSnapshot(
                        track_id=track.track_id,
                        velocidad=round(_speed(track.last_velocity), 2),
                        permanencia_segundos=max(0, int(now - track.first_seen)),
                        movimiento_erratico=track.movimiento_erratico,
                        es_nuevo=is_new,
                    ),
                )
            )

        return tracked

    def _match_track(self, detection: Detection, used_track_ids: set[str]) -> _Track | None:
        candidates = [
            track
            for track in self._tracks.values()
            if track.label == detection.label and track.track_id not in used_track_ids
        ]
        if not candidates:
            return None

        best = max(candidates, key=lambda track: _iou(track.box, detection.box))
        return best if _iou(best.box, detection.box) >= self._iou_threshold else None

    def _new_track(self, detection: Detection, now: float) -> _Track:
        index = self._counters.get(detection.label, 0) + 1
        self._counters[detection.label] = index
        track = _Track(
            track_id=f"{_normalize_label(detection.label)}_{index:04d}",
            label=detection.label,
            box=detection.box,
            first_seen=now,
            last_seen=now,
            last_center=_center(detection.box),
        )
        self._tracks[track.track_id] = track
        return track

    def _update_track(self, track: _Track, detection: Detection, now: float) -> None:
        elapsed = max(now - track.last_seen, 0.001)
        center = _center(detection.box)
        velocity = ((center[0] - track.last_center[0]) / elapsed, (center[1] - track.last_center[1]) / elapsed)
        if _direction_changed(track.last_velocity, velocity) and _speed(velocity) >= 80:
            track.movimiento_erratico = True

        track.box = detection.box
        track.last_seen = now
        track.last_center = center
        track.last_velocity = velocity
        track.observations += 1

    def _prune(self, now: float) -> None:
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if now - track.last_seen > self._max_lost_seconds
        ]
        for track_id in expired:
            del self._tracks[track_id]


@dataclass
class EventMemory:
    window_seconds: float = 24 * 60 * 60
    _events: list[tuple[float, str]] = field(default_factory=list)

    def snapshot(self, now: float) -> dict[str, int]:
        self._prune(now)
        alertas = sum(1 for _, risk in self._events if risk in {"alto", "critico"})
        return {
            "eventos_previos_24h": len(self._events),
            "alertas_previas_24h": alertas,
        }

    def remember(self, now: float, risk: str) -> None:
        self._events.append((now, risk.lower()))
        self._prune(now)

    def _prune(self, now: float) -> None:
        self._events = [
            item for item in self._events if now - item[0] <= self.window_seconds
        ]


def should_emit_event(
    snapshot: TrackingSnapshot,
    label: str,
    last_event_at: dict[str, float],
    now: float,
    cooldown_seconds: float,
) -> bool:
    if snapshot.es_nuevo or _normalize_label(label) in {"knife", "gun", "scissors"}:
        last_event_at[snapshot.track_id] = now
        return True

    last_seen = last_event_at.get(snapshot.track_id, 0)
    if cooldown_seconds <= 0 or now - last_seen >= cooldown_seconds:
        last_event_at[snapshot.track_id] = now
        return True

    return False


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _speed(velocity: tuple[float, float]) -> float:
    return hypot(velocity[0], velocity[1])


def _direction_changed(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return (a[0] * b[0] + a[1] * b[1]) < 0


def _normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_")
