const prepared = $("Preparar_Datos").first().json;
const rawOutput = $json.output ?? $json.text ?? $json.response ?? $json.message ?? $json;

const allowedRisk = ["BAJO", "MEDIO", "ALTO", "CRITICO"];
const riskRank = { BAJO: 0, MEDIO: 1, ALTO: 2, CRITICO: 3 };

function extractJson(value) {
  if (typeof value === "object" && value !== null) return value;
  const text = String(value ?? "").trim();
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : text;
  const start = candidate.indexOf("{");
  const end = candidate.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return {};
  try {
    return JSON.parse(candidate.slice(start, end + 1));
  } catch (error) {
    return {};
  }
}

function clamp(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function riskFromScore(score) {
  if (score >= 80) return "CRITICO";
  if (score >= 50) return "ALTO";
  if (score >= 25) return "MEDIO";
  return "BAJO";
}

function actionFromRisk(risk, confidence) {
  if (risk === "CRITICO") {
    return {
      accion: "ALERTA_CRITICA",
      prioridad: 10,
      notificar: true,
      canales: ["telegram", "dashboard_realtime"],
    };
  }
  if (risk === "ALTO") {
    return {
      accion: "ENVIAR_ALERTA",
      prioridad: 8,
      notificar: true,
      canales: ["dashboard_realtime"],
    };
  }
  if (risk === "MEDIO") {
    return {
      accion: "MONITOREAR",
      prioridad: 5,
      notificar: false,
      canales: [],
    };
  }
  const accion = confidence < 0.5 ? "IGNORAR_BAJA_CONFIANZA" : "REGISTRAR_EVENTO";
  return {
    accion,
    prioridad: confidence < 0.5 ? 1 : 2,
    notificar: false,
    canales: [],
  };
}

const llm = extractJson(rawOutput);
const baseScore = clamp(prepared.reglas?.score_base, 0, 100, 0);
const llmConfidence = clamp(llm.confianza_analisis, 0, 1, 0);
const llmScore = clamp(llm.score_sugerido ?? llm.score_riesgo, 0, 100, baseScore);
const baseRisk = riskFromScore(baseScore);
const llmRisk = allowedRisk.includes(String(llm.nivel_riesgo ?? "").toUpperCase())
  ? String(llm.nivel_riesgo).toUpperCase()
  : riskFromScore(llmScore);

let finalScore = baseScore;
if (llmConfidence >= 0.65 && llmScore > baseScore) {
  finalScore = Math.min(100, Math.round((baseScore * 0.7) + (llmScore * 0.3)));
}

let finalRisk = riskFromScore(finalScore);
if (llmConfidence >= 0.75 && riskRank[llmRisk] > riskRank[finalRisk]) {
  finalRisk = llmRisk;
  finalScore = Math.max(finalScore, { MEDIO: 25, ALTO: 50, CRITICO: 80 }[finalRisk] ?? finalScore);
}
if (riskRank[baseRisk] > riskRank[finalRisk]) {
  finalRisk = baseRisk;
}

const decision = actionFromRisk(finalRisk, prepared.evento.confianza);
const factoresIa = Array.isArray(llm.factores_ia) ? llm.factores_ia : [];
const resumenIa = String(llm.resumen ?? llm.analisis ?? "Analisis IA no disponible.").slice(0, 600);

return [
  {
    json: {
      status: "procesado",
      pipeline: [
        "AgentePercepcion",
        "AgenteTracking",
        "AgenteAnalisisIA",
        "AgenteRiesgo",
        "AgenteAccion",
        "AgenteMemoria",
      ],
      agente: "AgenteAnalisisIA",
      version: "0.4.0",
      entrada: prepared.evento,
      contexto: prepared.contexto,
      tracking: prepared.tracking,
      memoria: prepared.memoria,
      resultado: {
        riesgo: finalRisk,
        nivel_riesgo: finalRisk,
        severidad: finalRisk === "CRITICO" ? "CRITICA" : finalRisk,
        score: finalScore,
        score_riesgo: Math.round((finalScore / 100) * 10000) / 10000,
        factores: prepared.reglas.factores,
        factores_ia: factoresIa,
        resumen_ia: resumenIa,
        algoritmo: "risk_rules_v2_plus_llm_guarded",
        ia_confianza: llmConfidence,
        ia_raw_valida: Object.keys(llm).length > 0,
      },
      decision: {
        accion: decision.accion,
        accion_tomada: decision.accion,
        prioridad: decision.prioridad,
        notificar: decision.notificar,
        canales: decision.canales,
        guardar_en_supabase: true,
        requiere_revision_humana: ["ALTO", "CRITICO"].includes(finalRisk),
      },
      persistencia: {
        camara_id: prepared.evento.camara,
        objeto: prepared.evento.objeto,
        confianza: prepared.evento.confianza,
        score_riesgo: Math.round((finalScore / 100) * 10000) / 10000,
        nivel_riesgo: finalRisk,
        accion_tomada: decision.accion,
        alertas_previas_24h: prepared.memoria.alertas_previas_24h,
        detected_at: prepared.evento.hora,
        box: prepared.evento.box,
        contexto: prepared.contexto,
        tracking: prepared.tracking,
        memoria: prepared.memoria,
        resumen_ia: resumenIa,
      },
      mensaje: `${decision.accion}: ${finalRisk} con score ${Math.round((finalScore / 100) * 10000) / 10000}`,
      procesado_en: new Date().toISOString(),
    },
  },
];
