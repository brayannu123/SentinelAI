from __future__ import annotations

import time
from pathlib import Path

import cv2

from agente_percepcion.camera import Camera
from agente_percepcion.config import get_settings
from agente_percepcion.detector import YoloDetector, draw_detections
from agente_percepcion.events import DetectionEvent, N8nClient, SupabaseEventStore
from agente_percepcion.tracking import EventMemory, ObjectTracker, should_emit_event


def run() -> None:
    settings = get_settings()
    detector = YoloDetector(settings.model_path, settings.confidence, settings.classes)
    store = SupabaseEventStore(
        settings.supabase_url,
        settings.supabase_service_role_key,
        settings.supabase_detection_events_table,
    )
    n8n = N8nClient(settings.n8n_webhook_url)
    tracker = ObjectTracker(iou_threshold=settings.tracking_iou_threshold)
    memory = EventMemory()
    last_event_at: dict[str, float] = {}

    if settings.save_images:
        settings.image_dir.mkdir(parents=True, exist_ok=True)

    with Camera(settings.camera_index, backend=settings.camera_backend) as camera:
        while True:
            frame = camera.read()
            detections = detector.detect(frame)
            now = time.monotonic()
            tracked_detections = tracker.update(detections, now)
            person_tracks = [
                tracked for tracked in tracked_detections if tracked.detection.label == "person"
            ]

            for tracked in tracked_detections:
                detection = tracked.detection
                if not should_emit_event(
                    tracked.snapshot,
                    detection.label,
                    last_event_at,
                    now,
                    settings.event_cooldown_seconds,
                ):
                    continue

                image_path = _save_frame(settings.image_dir, frame) if settings.save_images else None
                memory_snapshot = memory.snapshot(now)
                related_person_id = (
                    tracked.snapshot.track_id
                    if detection.label == "person"
                    else _nearest_person_id(detection.box, person_tracks)
                )
                event = DetectionEvent.from_detection(
                    detection,
                    camera_name=settings.camera_name,
                    image_path=image_path,
                    contexto={
                        "zona": settings.scene_zone,
                        "iluminacion": settings.scene_lighting,
                        "cantidad_personas": sum(
                            1 for item in detections if item.label == "person"
                        ),
                    },
                    tracking={
                        "person_id": related_person_id,
                        "track_id": tracked.snapshot.track_id,
                        "velocidad": tracked.snapshot.velocidad,
                        "permanencia_segundos": tracked.snapshot.permanencia_segundos,
                        "movimiento_erratico": tracked.snapshot.movimiento_erratico,
                    },
                    memoria=memory_snapshot,
                )
                store.save(event)
                _send_to_n8n(n8n, event)
                memory.remember(now, event.riesgo)
                print(event.to_payload())

            cv2.imshow("SentinelAI - AgentePercepcion", draw_detections(frame, detections))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()


def _save_frame(image_dir: Path, frame) -> str:
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / f"evento_{int(time.time() * 1000)}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path)


def _nearest_person_id(box: tuple[int, int, int, int], person_tracks) -> str | None:
    if not person_tracks:
        return None

    cx, cy = _center(box)
    nearest = min(
        person_tracks,
        key=lambda item: _distance((cx, cy), _center(item.detection.box)),
    )
    return nearest.snapshot.track_id


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _send_to_n8n(n8n: N8nClient, event: DetectionEvent) -> None:
    result = n8n.send(event)
    if not result.sent:
        print(f"n8n no recibio el evento: {result.error}")
        return

    print(f"n8n respondio ({result.status_code}): {result.response}")


if __name__ == "__main__":
    run()
