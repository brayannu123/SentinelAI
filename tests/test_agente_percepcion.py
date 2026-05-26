from __future__ import annotations

import numpy as np

from agente_percepcion.detector import Detection, draw_detections
from agente_percepcion.events import DetectionEvent, N8nClient, risk_for_label
from agente_percepcion.tracking import ObjectTracker, should_emit_event


def test_detection_event_maps_to_supabase_row() -> None:
    detection = Detection(label="person", confidence=0.91, box=(10, 20, 200, 300))

    event = DetectionEvent.from_detection(detection, camera_name="PC-01")
    row = event.to_supabase_row()

    assert row["objeto"] == "person"
    assert row["camara_id"] == "PC-01"
    assert row["riesgo"] == "BAJO"
    assert row["box"] == [10, 20, 200, 300]


def test_risk_levels() -> None:
    assert risk_for_label("knife") == "alto"
    assert risk_for_label("gun") == "alto"
    assert risk_for_label("scissors") == "alto"
    assert risk_for_label("person") == "bajo"
    assert risk_for_label("cell phone") == "bajo"
    assert risk_for_label("cell_phone") == "bajo"
    assert risk_for_label("backpack") == "bajo"
    assert risk_for_label("bottle") == "bajo"


def test_n8n_without_webhook_does_not_send() -> None:
    event = DetectionEvent(
        objeto="person",
        confianza=0.91,
        hora="2026-05-26T00:00:00+00:00",
        camara="PC-01",
        riesgo="medio",
        box=(10, 20, 200, 300),
    )

    result = N8nClient(webhook_url=None).send(event)

    assert result.sent is False
    assert result.error is not None


def test_detection_event_includes_analysis_context() -> None:
    detection = Detection(label="knife", confidence=0.91, box=(10, 20, 200, 300))

    event = DetectionEvent.from_detection(
        detection,
        camera_name="PC-01",
        contexto={"zona": "entrada", "iluminacion": "baja", "cantidad_personas": 1},
        tracking={
            "person_id": "person_0001",
            "track_id": "knife_0001",
            "velocidad": 12.5,
            "permanencia_segundos": 3,
            "movimiento_erratico": False,
        },
        memoria={"eventos_previos_24h": 2, "alertas_previas_24h": 1},
    )

    payload = event.to_payload()

    assert payload["contexto"]["zona"] == "entrada"
    assert payload["tracking"]["person_id"] == "person_0001"
    assert payload["memoria"]["alertas_previas_24h"] == 1


def test_tracker_separates_people_with_different_boxes() -> None:
    tracker = ObjectTracker()

    tracked = tracker.update(
        [
            Detection(label="person", confidence=0.9, box=(0, 0, 100, 100)),
            Detection(label="person", confidence=0.88, box=(300, 0, 400, 100)),
        ],
        now=1.0,
    )

    assert [item.snapshot.track_id for item in tracked] == ["person_0001", "person_0002"]
    assert all(item.snapshot.es_nuevo for item in tracked)


def test_event_gate_uses_track_id_not_only_label() -> None:
    last_event_at: dict[str, float] = {}
    tracker = ObjectTracker()
    first, second = tracker.update(
        [
            Detection(label="person", confidence=0.9, box=(0, 0, 100, 100)),
            Detection(label="person", confidence=0.88, box=(300, 0, 400, 100)),
        ],
        now=1.0,
    )

    assert should_emit_event(first.snapshot, first.detection.label, last_event_at, 1.0, 5)
    assert should_emit_event(second.snapshot, second.detection.label, last_event_at, 1.0, 5)


def test_draw_detections_adds_bounding_box() -> None:
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    detection = Detection(label="person", confidence=0.91, box=(20, 30, 100, 90))

    output = draw_detections(frame.copy(), [detection])

    assert output.sum() > 0
    assert output[30, 20].sum() > 0
