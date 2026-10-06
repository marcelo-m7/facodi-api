# Contrato HTTP e objetos v1

Estado: especificação proposta; endpoints novos ainda não existem. Prefixo `/facodi/api/v1`. JSON REST em controllers `type="http"`, não envelope JSON-RPC. Isto permite respostas HTTP 202, 409 e 422 reais. Manter as três rotas legadas e corrigi-las com autenticação adequada.

## Endpoints

| Método / rota | Entrada | Resultado | Permissão |
| --- | --- | --- | --- |
| `POST /ingest` | `IngestRequest` | 202 `RunAccepted`; executa ingest/normalize | Pipeline Operator |
| `POST /enrich` | `EnrichRequest` com documento existente | 202 `RunAccepted` | Pipeline Operator + acesso ao artefacto |
| `POST /map` | `MapRequest` com enriquecimento existente | 202 `RunAccepted` | Pipeline Operator + acesso ao artefacto/alvos |
| `POST /pipeline/content` | `PipelineRequest` | 202 `RunAccepted`, processamento até revisão | Pipeline Operator |
| `GET /pipeline/{run_id}` | UUID | 200 `RunStatus` resumido | dono autorizado ou Manager |
| `GET /pipeline/{run_id}/artifacts/{artifact_id}` | UUIDs | 200 artefacto, até 2 MiB | acesso ao run + artefacto |
| `POST /pipeline/{run_id}/retry` | step key falhado/waiting_input + eventual `replacement_artifact_id` autorizado | 202 `RunAccepted` | Operator proprietário ou Manager |
| `POST /pipeline/{run_id}/cancel` | `{reason}` até 500 chars | 200 `RunStatus` | Operator proprietário ou Manager |
| `POST /pipeline/{run_id}/publish` | `{expected_revision}` | 202 `RunAccepted`; agenda ação explícita | eLearning Manager |
| `GET /health` — existente | nenhuma | 200 versão/status mínimo | público, sem config interna |

Não disponibilizar endpoints arbitrários de dispatch Python, código, função livre ou provider URL. A revisão ocorre pelas ações do backend de `facodi_learning`; novo endpoint de review não é requisito inicial. Formulário público/portal existente permanece no seu owner e usa os serviços internos, sem receber token técnico no browser.

## Autenticação e transporte

Todas as rotas novas usam `auth="bearer"`, exigem explicitamente `Authorization: Bearer ...` e validam grupos/ACL/record rules. Odoo bearer pode usar sessão quando o header está ausente; a API rejeita essa ausência para manter autenticação exclusivamente por token. TLS, CORS fechado por defeito, nenhum token na URL. CSRF desativado apenas nas rotas API com bearer obrigatório; rotas de formulário usam sessão e CSRF nativos.

Obrigatório `Content-Type: application/json` e header `Idempotency-Key` de 8 a 128 chars em todos os POST de comando. `X-Request-ID` externo opcional é validado como UUID; se ausente/inválido gerar UUID interno, nunca ecoar texto arbitrário. Preflight de JSON/autorização não faz chamadas de rede. Limite de body 256 KiB, incluindo checks quando Content-Length não existe; inputs grandes entram por attachment privado, não JSON inline.

| HTTP | Significado |
| --- | --- |
| 200 | leitura/cancelamento concluído ou replay de leitura |
| 202 | comando persistido para execução; replay retorna mesmo run e status 202 |
| 400 / 415 | JSON malformado ou media type errado |
| 401 / 403 | token ausente/inválido ou falta de papel |
| 404 | run/artefacto ausente ou inacessível, sem enumeração |
| 409 | idempotência conflituosa, versão desatualizada ou estado incompatível |
| 413 / 422 | payload excedido ou schema/valor inválido |
| 429 | quota por utilizador/provider; `Retry-After` |
| 503 | capacidade indisponível ou feature desativada |

Erro JSON: `{ "error": { "code": "idempotency_conflict", "message": "Request conflicts with an existing command.", "request_id": "UUID", "retryable": false } }`. Sem traceback, resposta bruta de provider, headers, token ou caminho local.

## Objetos Python

Dataclasses `frozen=True` com parse/validate explícito em `schemas/dto.py`; não depender apenas de type hints. JSON serializável, datetime UTC ISO8601, UUID strings, unknown fields rejeitados, strings bounded e números finitos. Estes nomes são contrato entre serviços, não novos modelos académicos.

| DTO | Campos obrigatórios / opcionais |
| --- | --- |
| `ContentSource` | `kind` (`youtube`, `document`); `url` para YouTube OU `attachment_id` para documento; `preferred_languages` (1–4 códigos, default `pt,en`); URL/attachment mutuamente exclusivos |
| `PipelineContext` | `submission_id`, `channel_id`, `slide_id`, `curriculum_unit_ids` opcionais; servidor resolve ator/company/website; até 20 UCs autorizadas |
| `TranscriptSegment` | `segment_id`, `text`, `start_seconds >=0`, `duration_seconds >=0`; times reais ou ausentes em documento, nunca inventados |
| `ContentDocument` | `schema_version=1`, `source`, `title`, `markdown`, `language` nullable, `segments`, `transcript_status`, `analysis_depth`, `provenance`, `warnings` |
| `Provenance` | `provider`, `provider_version`, `service_version`, `source_identity`, `retrieved_at`, `content_sha256`, `language_origin`, `is_generated`, `is_translated`; desconhecidos nullable |
| `ContentChunk` | `chunk_id`, `text`, `segment_ids`, `char_start`, `char_end`; offsets no Markdown normalizado |
| `EnrichedDocument` | `schema_version=1`, `document_artifact_id`, `chunks`, `summary` nullable, `concepts`, `topics`, `analysis_depth`, `model_provenance` nullable |
| `EvidenceReference` | `chunk_id`, `segment_ids`, `quote` até 500 chars; referências verificadas contra input |
| `MappingCandidate` | `candidate_id`, `target_model`, `target_id`, `relation`, `ranking_score [0,1]`, `rationale`, `evidence`, `snapshot_id`; target enum limitado pelo servidor |
| `MappingResult` | `schema_version=1`, `enriched_artifact_id`, `snapshot_id`, `ranking_version`, `candidates`, `unmapped_concepts`, `warnings`; lista vazia válida |
| `RunAccepted` | `run_id`, `state`, `capability`, `pipeline_version`, `status_url`, `request_id`; sem task ID interno para portal |
| `RunStatus` | `run_id`, `state`, `revision`, `steps`, `artifact_refs`, `safe_error`, timestamps; seleção limitada ao papel |

`transcript_status`: `available`, `missing`, `blocked`, `not_applicable`. `analysis_depth`: `metadata`, `transcript`, `document`. A mesma profundidade propaga-se ao enriquecimento. Traduzir transcrição é opt-in de configuração; não mudar linguagem original silenciosamente.

Tipos internos usados no plano: `RequestDTO` é a união dos quatro inputs; `IngestionPolicy` contém allowlist/timeouts/limites fixados em execution-security.md; `EnrichmentProfile` resolve o profile versionado configurado em facodi_ai, com modelo/prompt e limites, nunca valores livres do cliente. `CurriculumSnapshot` contém UUID, company/website, revision hash, retrieved_at e lista autorizada de alvos com metadata lexical/evidência oficial. `PipelineRun`/`PipelineStep` são records ORM novos; `StepOutcome` é DTO com state, artifact_refs, safe_error e next_retry_at. `EditorialHandoff` contém referências autorizadas a job/result e propostas existentes. `VerifiedEvent` contém provider, event_id e conteúdo validado minimizado. `ExistingNormalizedAnalysisOutput` é o payload normalizado do serviço analysis existente, não schema paralelo; `ExistingAnalysisResult` é o record `facodi.learning.analysis.result` correspondente. `BenchmarkScenario` nomeia input, cache state e provider mode; `BenchmarkReport` guarda configuração/amostra/latências por etapa.

### Inputs por capability

`IngestRequest = {source, context?}`. `EnrichRequest = {document_artifact_id, profile="default_v1"}`. `MapRequest = {enriched_artifact_id, scope="all"|"courses"|"curriculum", context?}`. `PipelineRequest = {pipeline="youtube_video_v1"|"document_v1", source, context?}`. Profile/pipeline aceitam exclusivamente nomes presentes no registry. O servidor nunca aceita `state`, `reviewed_by_id`, `company_id`, `provider_url`, `prompt` ou `sudo` no input.

### Exemplo de comando

```http
POST /facodi/api/v1/pipeline/content
Authorization: Bearer <token técnico>
Content-Type: application/json
Idempotency-Key: video-demo-20261006

{
  "pipeline": "youtube_video_v1",
  "source": {
    "kind": "youtube",
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "preferred_languages": ["pt", "en"]
  },
  "context": {"submission_id": 123, "channel_id": 41}
}
```

IDs e URL são ilustrativos, não fixtures nem autorização para usar registos reais. Resposta 202:

```json
{
  "run_id": "559f6b1b-2d14-4b91-a5ad-94fe6419a1c3",
  "state": "queued",
  "capability": "pipeline/content",
  "pipeline_version": "youtube_video_v1",
  "status_url": "/facodi/api/v1/pipeline/559f6b1b-2d14-4b91-a5ad-94fe6419a1c3",
  "request_id": "c7f10c8c-b745-43c7-b946-bb616a27e2ac"
}
```

## Máquina de estados

Run: `queued -> running -> review_required -> ready -> published` no pipeline completo. Capability isolada termina em `succeeded`. Da execução pode surgir `waiting_input`, `failed` ou `cancelled`; retry autorizado volta a `queued`. `waiting_input` pode receber attachment novo e cria nova versão de artefacto. Aprovação/rejeição de sugestões é estado editorial do modelo existente, nunca imposto pelo cliente.

Step: `pending`, `running`, `succeeded`, `waiting_input`, `retry_wait`, `failed`, `skipped`, `cancelled`. Step humano `review` fica pending até decisão; run fica review_required. `publish` só é elegível com comando de Manager e expected_revision atual. Dependências técnicas aceitam apenas succeeded ou skipped autorizado pelo registry; failed/cancelled nunca desbloqueiam uma etapa.

Revisão increments `revision` sob lock. Publicação revalida no worker se a decisão, alvos e revisão continuam válidos. Operação completa e side effect persistem na mesma transação ORM; falha não deixa o run publicado sem conteúdo publicado.
