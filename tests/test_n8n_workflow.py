from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_agente_analisis_workflow_is_valid_json() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))

    assert workflow["name"] == "AgenteAnalisis"
    assert workflow["active"] is False


def test_agente_analisis_workflow_has_core_nodes() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))
    node_names = {node["name"] for node in workflow["nodes"]}

    assert "Webhook - Evento Percepcion" in node_names
    assert "Normalizar Evento" in node_names
    assert "AgenteRiesgo - Score Hibrido" in node_names
    assert "AgenteAccion - Preparar Respuesta" in node_names
    assert "Responder a AgentePercepcion" in node_names


def test_agente_analisis_workflow_connections_are_complete() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))
    connections = workflow["connections"]

    assert "Webhook - Evento Percepcion" in connections
    assert connections["Webhook - Evento Percepcion"]["main"][0][0]["node"] == "Normalizar Evento"
    assert connections["Normalizar Evento"]["main"][0][0]["node"] == "AgenteRiesgo - Score Hibrido"
    assert (
        connections["AgenteRiesgo - Score Hibrido"]["main"][0][0]["node"]
        == "AgenteAccion - Preparar Respuesta"
    )
    assert (
        connections["AgenteAccion - Preparar Respuesta"]["main"][0][0]["node"]
        == "Responder a AgentePercepcion"
    )


def test_agente_analisis_workflow_returns_persistence_contract() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))
    code_nodes = {node["name"]: node["parameters"]["jsCode"] for node in workflow["nodes"] if node["type"].endswith(".code")}
    action_code = code_nodes["AgenteAccion - Preparar Respuesta"]

    assert "persistencia" in action_code
    assert "score_riesgo" in action_code
    assert "nivel_riesgo" in action_code
    assert "accion_tomada" in action_code
    assert "detected_at" in action_code
    assert "tracking: data.tracking" in action_code
    assert "memoria: data.memoria" in action_code


def test_agente_analisis_workflow_uses_low_base_score_for_cell_phone() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))
    code_nodes = {node["name"]: node["parameters"]["jsCode"] for node in workflow["nodes"] if node["type"].endswith(".code")}
    risk_code = code_nodes["AgenteRiesgo - Score Hibrido"]

    assert "cell_phone: 5" in risk_code
    assert "person: 10" in risk_code
    assert "knife: 60" in risk_code
    assert "gun: 80" in risk_code


def test_agente_analisis_workflow_uses_tracking_context() -> None:
    workflow = json.loads(Path("n8n/AgenteAnalisis.workflow.json").read_text(encoding="utf-8"))
    code_nodes = {node["name"]: node["parameters"]["jsCode"] for node in workflow["nodes"] if node["type"].endswith(".code")}
    normalize_code = code_nodes["Normalizar Evento"]
    risk_code = code_nodes["AgenteRiesgo - Score Hibrido"]
    action_code = code_nodes["AgenteAccion - Preparar Respuesta"]

    assert "cantidad_personas" in normalize_code
    assert "track_id" in normalize_code
    assert "persona_asociada_objeto_peligroso" in risk_code
    assert "risk_rules_v2" in risk_code
    assert "AgenteTracking" in action_code


def test_n8n_test_payloads_are_valid_json() -> None:
    for path in Path("n8n").glob("test_payload_*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "objeto" in payload
        assert "confianza" in payload


def test_n8n_ia_code_snippets_are_present() -> None:
    prepare = Path("n8n/code/Preparar_Datos_IA.js")
    parser = Path("n8n/code/Parsear_JSON_LLM.js")
    prompt = Path("n8n/code/SYSTEM_PROMPT_AGENTE_ANALISIS_IA.md")

    assert prepare.exists()
    assert parser.exists()
    assert prompt.exists()
    assert "prompt_ia" in prepare.read_text(encoding="utf-8")
    assert "risk_rules_v2_plus_llm_guarded" in parser.read_text(encoding="utf-8")
    assert "Responde solo JSON valido" in prompt.read_text(encoding="utf-8")


def test_n8n_ia_code_snippets_have_valid_javascript_syntax() -> None:
    for path in [
        Path("n8n/code/Preparar_Datos_IA.js"),
        Path("n8n/code/Parsear_JSON_LLM.js"),
    ]:
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
