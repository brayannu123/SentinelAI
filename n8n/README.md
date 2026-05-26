# AgenteAnalisis en n8n

Este workflow recibe eventos del `AgentePercepcion`, normaliza el payload, calcula un score de riesgo y responde con una accion recomendada.

n8n no hace IA pesada. En esta arquitectura n8n orquesta, decide acciones y conecta alertas. La vision artificial, tracking y prediccion pesada deben vivir en Python/FastAPI.

## Flujo

```text
Webhook - Evento Percepcion
  -> Normalizar Evento
  -> AgenteRiesgo - Score Hibrido
  -> AgenteAccion - Preparar Respuesta
  -> Responder a AgentePercepcion
```

## Flujo IA recomendado

Si usas el flujo visual con Groq como en tu captura, dejalo asi:

```text
AgentePercepcion_Webhook
  -> Preparar_Datos
  -> AgenteAnalisis_IA
  -> Parsear_JSON_LLM
  -> guardar / alerta / respuesta

Groq_Chat_Model
  -> AgenteAnalisis_IA
```

Codigo para cada nodo:

- `Preparar_Datos`: pega `n8n/code/Preparar_Datos_IA.js`.
- `AgenteAnalisis_IA`: usa el prompt de sistema de `n8n/code/SYSTEM_PROMPT_AGENTE_ANALISIS_IA.md`.
- En el campo de entrada del agente IA, envia `{{$json.prompt_ia}}`.
- `Parsear_JSON_LLM`: pega `n8n/code/Parsear_JSON_LLM.js`.

El nodo IA solo recomienda y explica. El nodo `Parsear_JSON_LLM` valida la respuesta,
combina IA con reglas y devuelve el JSON final. Asi evitamos que una respuesta mal
formada del modelo rompa el flujo o tome decisiones sin control.

## Importar

1. Abre n8n.
2. Ve a `Workflows`.
3. Selecciona `Import from File`.
4. Importa `n8n/AgenteAnalisis.workflow.json`.
5. Activa el workflow para usar la URL de produccion.

## URLs

Workflow activo:

```text
http://localhost:5678/webhook/sentinel-analysis
```

Prueba desde el editor con `Listen for test event`:

```text
http://localhost:5678/webhook-test/sentinel-analysis
```

## Contrato minimo recibido desde la camara

```json
{
  "objeto": "knife",
  "confianza": 0.91,
  "hora": "2026-05-26T20:30:00.000000+00:00",
  "camara": "PC-01",
  "box": [10, 20, 200, 300],
  "imagen": null
}
```

## Contrato enriquecido desde AgentePercepcion

Cuando ejecutas `python -m agente_percepcion.main`, el agente ya envia contexto,
tracking y memoria. Los archivos `test_payload_*.json` son solo para validar n8n
sin abrir la camara.

```json
{
  "objeto": "knife",
  "confianza": 0.91,
  "hora": "2026-05-26T23:30:00.000000+00:00",
  "camara": "PC-01",
  "box": [10, 20, 200, 300],
  "imagen": null,
  "contexto": {
    "zona": "entrada_principal",
    "iluminacion": "baja",
    "cantidad_personas": 1
  },
  "tracking": {
    "person_id": "person_0001",
    "track_id": "knife_0001",
    "velocidad": 8.2,
    "permanencia_segundos": 420,
    "movimiento_erratico": true
  },
  "memoria": {
    "eventos_previos_24h": 12,
    "alertas_previas_24h": 2
  }
}
```

## Respuesta esperada

```json
{
  "status": "procesado",
  "pipeline": [
    "AgentePercepcion",
    "AgenteAnalisis",
    "AgenteRiesgo",
    "AgenteAccion",
    "AgenteMemoria"
  ],
  "resultado": {
    "riesgo": "CRITICO",
    "nivel_riesgo": "CRITICO",
    "severidad": "CRITICA",
    "score": 100,
    "score_riesgo": 1.0,
    "algoritmo": "risk_rules_v2"
  },
  "decision": {
    "accion": "ALERTA_CRITICA",
    "accion_tomada": "ALERTA_CRITICA",
    "prioridad": 10,
    "notificar": true,
    "canales": ["telegram", "dashboard_realtime"],
    "guardar_en_supabase": true,
    "requiere_revision_humana": true
  }
}
```

El objeto `persistencia` ya viene preparado para guardar el evento enriquecido en Supabase:

```json
{
  "camara_id": "PC-01",
  "objeto": "knife",
  "confianza": 0.91,
  "score_riesgo": 1.0,
  "nivel_riesgo": "CRITICO",
  "accion_tomada": "ALERTA_CRITICA",
  "alertas_previas_24h": 2,
  "detected_at": "2026-05-26T20:30:00.000000+00:00",
  "box": [10, 20, 200, 300],
  "contexto": {
    "zona": "entrada_principal",
    "iluminacion": "baja"
  },
  "tracking": {
    "person_id": "person_0001",
    "track_id": "knife_0001"
  }
}
```

## Reglas actuales

El score va de `0` a `100`.

- `gun`: base critica.
- `knife`: base alta.
- `scissors`: base media-alta.
- `person`, `cell_phone`, `backpack`, `car`, `truck`, `motorcycle`: base baja.
- Confianza alta suma puntos.
- Confianza baja resta puntos.
- Horario nocturno suma puntos.
- Baja iluminacion suma puntos.
- Velocidad alta suma puntos.
- Movimiento erratico suma puntos.
- Permanencia mayor a 5 o 15 minutos suma puntos.
- Historial reciente de eventos o alertas suma puntos.

Niveles:

- `0-24`: `BAJO`
- `25-49`: `MEDIO`
- `50-79`: `ALTO`
- `80-100`: `CRITICO`

Importante: una persona o un celular no son sospechosos por si solos. Suben de nivel solo con contexto, tracking, horario, objeto peligroso o historial.

## Como debe quedar en n8n para camara real

1. Importa `n8n/AgenteAnalisis.workflow.json`.
2. Abre el nodo `Webhook - Evento Percepcion`.
3. Confirma metodo `POST` y path `sentinel-analysis`.
4. Guarda el workflow.
5. Activa el workflow.
6. En `.env`, usa `SENTINEL_N8N_WEBHOOK_URL=http://localhost:5678/webhook/sentinel-analysis`.
7. Ejecuta la camara con `python -m agente_percepcion.main`.

No uses `/webhook-test/sentinel-analysis` con la camara real salvo que tengas el
editor de n8n abierto esperando un unico evento de prueba.

## Pruebas con curl

Alto riesgo:

```powershell
curl.exe -X POST http://localhost:5678/webhook-test/sentinel-analysis -H "Content-Type: application/json" --data-binary "@n8n/test_payload_knife.json"
```

Caso normal:

```powershell
curl.exe -X POST http://localhost:5678/webhook-test/sentinel-analysis -H "Content-Type: application/json" --data-binary "@n8n/test_payload_normal.json"
```

## Prueba recomendada desde Python

Antes de abrir la camara, prueba n8n asi:

```powershell
python tools/test_n8n_webhook.py --payload n8n/test_payload_knife.json
```

Si el workflow esta activo, usa la URL productiva:

```powershell
python tools/test_n8n_webhook.py --url http://localhost:5678/webhook/sentinel-analysis --payload n8n/test_payload_knife.json
```

## Si parece que no pasa nada

- Para `/webhook-test/sentinel-analysis`, n8n debe estar en `Listen for test event`.
- Para `/webhook/sentinel-analysis`, el workflow debe estar activo.
- Si Python muestra `connection refused`, n8n no esta corriendo en `localhost:5678`.
- Si Python muestra `404`, estas usando la URL equivocada o el workflow no esta activo.
- Si Python detecta objetos pero no envia eventos seguido, revisa `SENTINEL_EVENT_COOLDOWN_SECONDS`.

## Siguientes fases

- `AgenteTracking`: ByteTrack/DeepSORT en Python.
- `AgenteMemoria`: consultas a Supabase para historial real.
- `AgentePrediccion`: modelo ML con scikit-learn cuando exista dataset suficiente.
- `AgenteAccion`: Telegram, Discord, email y dashboard realtime.
