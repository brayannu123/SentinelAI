const payload = $json.body ?? $json;
const contexto = payload.contexto ?? payload.context ?? {};
const tracking = payload.tracking ?? {};
const memoria = payload.memoria ?? payload.memory ?? {};

function normalizeObject(value) {
  return String(value ?? "").trim().toLowerCase().replace(/\s+/g, "_");
}

function numberOrDefault(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function boolOrDefault(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (value === undefined || value === null || value === "") return fallback;
  return ["1", "true", "yes", "si", "on"].includes(String(value).toLowerCase());
}

function addFactor(factors, points, code, detail) {
  factors.push({ code, points, detail });
  return points;
}

const objeto = normalizeObject(payload.objeto ?? payload.object);
const confianza = numberOrDefault(payload.confianza ?? payload.confidence);
const hora = String(payload.hora ?? payload.detected_at ?? new Date().toISOString());
const eventTime = new Date(hora);
const horaLocal = Number.isNaN(eventTime.getTime()) ? new Date().getHours() : eventTime.getHours();
const noche = horaLocal >= 22 || horaLocal <= 5;

const evento = {
  objeto,
  confianza,
  camara: String(payload.camara ?? payload.camera ?? payload.camara_id ?? "PC-01"),
  hora,
  box: payload.box ?? null,
  imagen: payload.imagen ?? payload.image_path ?? payload.imagen_url ?? null,
};

const escena = {
  zona: contexto.zona ?? contexto.zone ?? "sin_zona",
  iluminacion: normalizeObject(contexto.iluminacion ?? contexto.lighting ?? "desconocida"),
  cantidad_personas: numberOrDefault(contexto.cantidad_personas ?? contexto.people_count),
  hora_local: horaLocal,
  noche,
};

const seguimiento = {
  person_id: tracking.person_id ?? tracking.track_id ?? null,
  track_id: tracking.track_id ?? tracking.person_id ?? null,
  velocidad: numberOrDefault(tracking.velocidad ?? tracking.speed),
  permanencia_segundos: numberOrDefault(
    tracking.permanencia_segundos ?? tracking.loitering_seconds,
  ),
  movimiento_erratico: boolOrDefault(tracking.movimiento_erratico ?? tracking.erratic_motion),
};

const historial = {
  eventos_previos_24h: numberOrDefault(
    memoria.eventos_previos_24h ?? memoria.previous_events_24h,
  ),
  alertas_previas_24h: numberOrDefault(
    memoria.alertas_previas_24h ?? memoria.previous_alerts_24h,
  ),
};

const baseScores = {
  gun: 80,
  knife: 60,
  scissors: 40,
  backpack: 18,
  person: 10,
  cell_phone: 5,
  car: 8,
  truck: 8,
  motorcycle: 10,
};
const dangerousObjects = new Set(["knife", "gun", "scissors"]);
const factors = [];
let score = 0;

if (!objeto) {
  score += addFactor(factors, 5, "payload_incompleto", "No se recibio objeto detectable.");
} else if (Object.prototype.hasOwnProperty.call(baseScores, objeto)) {
  score += addFactor(
    factors,
    baseScores[objeto],
    dangerousObjects.has(objeto) ? "objeto_peligroso" : "objeto_base",
    `Objeto detectado: ${objeto}.`,
  );
} else {
  score += addFactor(factors, 8, "objeto_observado", `Objeto observado sin regla critica: ${objeto}.`);
}

if (dangerousObjects.has(objeto) && seguimiento.person_id) {
  score += addFactor(
    factors,
    10,
    "persona_asociada_objeto_peligroso",
    `Objeto peligroso asociado a ${seguimiento.person_id}.`,
  );
}
if (confianza >= 0.9) score += addFactor(factors, 10, "alta_confianza", `Confianza alta: ${confianza}.`);
else if (confianza >= 0.7) score += addFactor(factors, 5, "confianza_media", `Confianza aceptable: ${confianza}.`);
else score += addFactor(factors, -10, "baja_confianza", `Confianza baja: ${confianza}.`);

if (escena.noche) score += addFactor(factors, 15, "horario_nocturno", "Evento detectado en horario nocturno.");
if (["baja", "oscura", "low", "dark"].includes(escena.iluminacion)) {
  score += addFactor(factors, 10, "baja_iluminacion", "Condicion de baja iluminacion.");
}
if (seguimiento.velocidad >= 7) {
  score += addFactor(factors, 12, "movimiento_rapido", `Velocidad elevada: ${seguimiento.velocidad}.`);
}
if (seguimiento.movimiento_erratico) {
  score += addFactor(factors, 15, "movimiento_erratico", "Movimiento erratico reportado por tracking.");
}
if (seguimiento.permanencia_segundos >= 900) {
  score += addFactor(factors, 25, "permanencia_sospechosa", "Permanencia mayor o igual a 15 minutos.");
} else if (seguimiento.permanencia_segundos >= 300) {
  score += addFactor(factors, 10, "permanencia_media", "Permanencia mayor o igual a 5 minutos.");
}
if (historial.alertas_previas_24h >= 2) {
  score += addFactor(factors, 15, "historial_alertas", "La camara/zona tiene alertas recientes.");
}
if (historial.eventos_previos_24h >= 10) {
  score += addFactor(factors, 8, "historial_eventos", "La camara/zona tiene actividad reciente alta.");
}

score = Math.max(0, Math.min(100, Math.round(score)));

const evidencia = {
  evento,
  contexto: escena,
  tracking: seguimiento,
  memoria: historial,
  reglas: {
    score_base: score,
    factores: factors,
    objetos_peligrosos: Array.from(dangerousObjects),
  },
};

return [
  {
    json: {
      ...evidencia,
      prompt_ia: JSON.stringify(evidencia, null, 2),
    },
  },
];
