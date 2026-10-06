# FACODI API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Subagents only if explicitly selected by the user. Steps use checkbox syntax for tracking.

**Goal:** implementar num único addon Python ingestão, enriquecimento, mapping e publicação explicitamente revista, com espelho em Odoo Project.

**Architecture:** controllers REST enfileiram runs; serviços tipados dentro do addon executam por cron limitado. Artefactos pre-slide são técnicos; domínio e decisões continuam em facodi_learning e standard eLearning. Project acompanha cada execução e etapa.

**Tech Stack:** Odoo 19 Community, Python do runtime Odoo, dataclasses, MarkItDown, youtube-transcript-api, facodi_ai existente, PostgreSQL e ir.cron.

**Spec:** [2026-10-06-facodi-api-design.md](../specs/2026-10-06-facodi-api-design.md). **Estado:** plano proposto; nenhum código de produto implementado nesta entrega. Backlog autorizado pelo pedido atual; execução de código é etapa posterior.

## Global Constraints

- Odoo 19 Community; sem Studio/Enterprise obrigatório.
- Um addon novo facodi_api; facodi_learning/facodi_ai mantêm ownership e não dependem de API.
- slide.channel e slide.slide canónicos; sem novos modelos de curso/progresso/ECTS.
- Revisão Manager explícita; task Done não aprova nem publica.
- Header bearer obrigatório; HTTP JSON assíncrono 202; Idempotency-Key em comandos.
- Cron tick 1 minuto, concorrência 1, máximo 3 tentativas; rede com deadline total 20 s.
- Body 256 KiB, attachment 10 MiB, Markdown 2 MiB, máximo 10 000 segmentos/200 chunks.
- Source labels em inglês, tradução PO nativa PT/ES/FR; segredos/artefactos privados.
- Provider congelado por run; seleção local explícita; sem duplicar scheduler job/run.
- db -> migrate -> odoo, recurso Coolify e postgres-data/odoo-data preservados.

## Review Focus

1. Sessão autenticada sem bearer ainda deve ser 401; teste A09.
2. Legenda ausente com descrição longa não é vídeo analisado; teste A05.
3. Cancel de Project fecha dependências standard, mas não desbloqueia scheduler; teste A04.
4. Cancel/crash durante I/O não deve persistir resultado/publicação tardia; teste A03.
5. Secret Supabase removido num segundo migrate não deve apagar seleção local; teste D02.

## Verificação e preparação

Código será desenvolvido no owner API, em checkout isolado. Ler AGENTS atual de deploy antes de alterar integração. Unitários puros em tests/ não dependem de Odoo. Testes ORM/HTTP ficam em facodi_api/tests/ com __init__.py atualizado. Os nomes seguintes são ficheiros/testes a criar; não afirmar que já passam.

Comando unitário futuro: python3 -m unittest discover -s tests -v. Testes Odoo em base descartável: odoo -d facodi_api_test --test-enable --test-tags /facodi_api -u facodi_api --stop-after-init, com configuração de addons/DB própria do ambiente dev. Instalação inicial usa -i facodi_api. Não apontar esses comandos à base facodi produtiva.

---

### Task 1: A01 — Reforçar autenticação, idempotência e isolamento dos webhooks existentes

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/2. **Prioridade:** P0.

**Files:** `facodi_api/controllers/api.py`; `facodi_api/models/api_event.py`; `facodi_api/security/ir.model.access.csv`; `facodi_api/tests/test_webhook_security.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: especificação e contratos v1.
- Produces: verify_webhook(provider: str, raw_body: bytes, headers: Mapping[str, str]) -> VerifiedEvent.

**Decisões de implementação:** Verificar bytes originais antes do parse; Supabase exige secret/assinatura e event ID único; Stripe usa construct_event e signing secret. Sem configuração rejeitar (503). Não mudar operações de checkout nem permitir que eventos de pagamento alterem conteúdo.

- [ ] Escrever os testes discriminantes: test_missing_secret_fails_closed; test_missing_signature_rejected; test_invalid_signature_rejected; test_signed_raw_bytes_accepted; test_event_replay_unique.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Secret/assinatura ausentes ou inválidos não criam facodi.api.event.
- [ ] Assinatura válida gera uma única receção; replay é reconhecido sem duplo efeito.
- [ ] Dados/payloads e segredos não aparecem em erros públicos; leitura de evento exige acesso interno apropriado.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 2: A02 — Definir DTOs tipados e validação dos contratos ingest/enrich/map/pipeline v1

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/3. **Prioridade:** P0.

**Files:** `facodi_api/schemas/__init__.py`; `facodi_api/schemas/dto.py`; `tests/test_contracts.py`; `docs/facodi-api/contracts.md`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: especificação e contratos v1.
- Produces: parse_request(capability: str, payload: Mapping[str, object]) -> IngestRequest | EnrichRequest | MapRequest | PipelineRequest.

**Decisões de implementação:** Dataclasses frozen, schema_version=1, allowlists e limites exatos da proposta; objects ContentSource, ContentDocument, EnrichedDocument, MappingResult. Gerar JSON Schema/OpenAPI validável a partir do contrato final e manter documentação/testes alinhados.

- [ ] Escrever os testes discriminantes: test_roundtrip_v1; test_source_exclusive; test_unknown_reserved_fields; test_nonfinite_score; test_invalid_evidence_reference.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Unknown/reserved fields, NaN/Infinity, IDs/tipos errados e source URL+attachment simultâneos são rejeitados.
- [ ] Transcript segments conservam timestamps; evidence references apontam a chunks válidos.
- [ ] Inputs serializam/deserializam sem perder versão/provenance e validam limites de 256 KiB/2 MiB.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 3: A03 — Implementar runs, etapas e artefactos imutáveis com runner cron recuperável

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/4. **Prioridade:** P0.

**Files:** `facodi_api/models/pipeline_run.py`; `facodi_api/models/pipeline_step.py`; `facodi_api/models/pipeline_artifact.py`; `facodi_api/services/pipeline/registry.py`; `facodi_api/services/pipeline/runner.py`; `facodi_api/data/ir_cron.xml`; `facodi_api/tests/test_pipeline_runner.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A02 (https://github.com/marcelo-m7/facodi-api/issues/3).
- Produces: enqueue(capability: str, dto: RequestDTO, actor_id: int, idempotency_key: str) -> PipelineRun; execute_next_step(run_id: int) -> StepOutcome.

**Decisões de implementação:** Registry fixo youtube_video_v1/document_v1; máquina de estados, unique SQL, hash de comando, artefactos, checkpoints, retry 3 total com 60/180s de schedule. Cron 1min, concorrência1; lock transacional ou lease fenced se libertar I/O. Sem env/cursor compartilhado entre threads.

- [ ] Escrever os testes discriminantes: test_concurrent_replay_one_run; test_key_conflict; test_crash_resume; test_cancel_prevents_commit; test_retry_schedule_no_sleep; test_failed_dependency_blocked.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Dois comandos simultâneos iguais têm um run; key/body diferente gera 409.
- [ ] Crash/restart/cancel durante I/O não duplica efeitos nem sobrepõe output novo.
- [ ] Failed/cancelled bloqueiam descendentes; etapas opcionais skipped só pelo registry.
- [ ] Subprocesso/conversão/provider tem deadline total; cron retorna ao esgotar budget; tentativas mantêm auditoria.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 4: A04 — Espelhar cada execução em Project standard com tarefas, subtarefas e dependências

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/5. **Prioridade:** P0.

**Files:** `facodi_api/models/project_task.py`; `facodi_api/services/project_bridge.py`; `facodi_api/data/pipeline_project.xml`; `facodi_api/views/project_task_views.xml`; `facodi_api/security/pipeline_security.xml`; `facodi_api/tests/test_project_bridge.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A03 (https://github.com/marcelo-m7/facodi-api/issues/4).
- Produces: sync_run(run: PipelineRun) -> project.task; sync_step(step: PipelineStep) -> project.task.

**Decisões de implementação:** Projeto privado, parent_id/depend_on_ids standard, stages dedicados e atividades deduplicadas. Novas ligações readonly/copy=False. Retry usa mesmas tasks. Estado técnico permanece autoridade; arrastar card não aprova/publica.

- [ ] Escrever os testes discriminantes: test_one_parent_and_eight_steps; test_retry_reuses_task; test_portal_private; test_drag_done_does_not_publish; test_copy_detaches_links; test_cancelled_dependency_does_not_unblock.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Um run possui uma tarefa principal e cada etapa habilitada uma subtarefa única, criadas atomicamente.
- [ ] Pipeline completo cria oito etapas descritas; capabilities isoladas só as habilitadas.
- [ ] Portal não lê tasks/attachments/chatter técnico; Manager vê smart buttons com checks do alvo.
- [ ] Cópia/apagamento/movimento de task não duplica run nem contorna revisão; tasks normais continuam utilizáveis.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 5: A05 — Ingerir YouTube com MarkItDown e transcrição temporal por adapter seguro

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/6. **Prioridade:** P0.

**Files:** `facodi_api/services/ingestion/service.py`; `facodi_api/services/ingestion/youtube.py`; `facodi_api/services/ingestion/markitdown.py`; `facodi_api/services/ingestion/safe_fetch.py`; `facodi_api/services/normalization.py`; `requirements.in`; `requirements.lock`; `tests/test_ingestion.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A02 (https://github.com/marcelo-m7/facodi-api/issues/3), A03 (https://github.com/marcelo-m7/facodi-api/issues/4).
- Produces: ingest(source: ContentSource, policy: IngestionPolicy) -> ContentDocument; normalize(document: ContentDocument) -> ContentDocument.

**Decisões de implementação:** MarkItDown isolado para conversão; youtube-transcript-api preserva segmentos. Normalizar video ID, idiomas, provenance e hash. Metadata-only não é análise completa. Ficheiros documentais começam por attachment autorizado; document_v1 PDF/DOCX integra em M2 com mesmo contrato.

- [ ] Escrever os testes discriminantes: test_timestamp_preservation; test_metadata_not_transcript; test_blocked_waiting_input; test_manual_transcript_resume; test_private_redirect; test_dns_rebinding; test_oversize_conversion.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Fixture YouTube com legenda devolve Markdown e segments/start/duration coerentes; não busca transcrição duas vezes.
- [ ] Ausência de legenda/IP blocked fica waiting_input com motivo distinto; manual transcript é nova evidência privada.
- [ ] SSRF/DNS rebinding/redirects privados, formatos não aceites e oversize são bloqueados antes do conversor.
- [ ] Resolver lock/hashes compatível com o Python real de odoo:19.0; plugins/all extras não são instalados implicitamente.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 6: A06 — Enriquecer Markdown com chunks e conceitos rastreáveis via facodi_ai

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/7. **Prioridade:** P1.

**Files:** `facodi_api/services/enrichment.py`; `facodi_api/schemas/dto.py`; `tests/test_enrichment.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A05 (https://github.com/marcelo-m7/facodi-api/issues/6).
- Produces: enrich(document: ContentDocument, profile: EnrichmentProfile) -> EnrichedDocument.

**Decisões de implementação:** Chunks 4000chars/overlap200/max200; termos baseline sem IA, resumo/conceitos estruturados por serviço existente facodi_ai quando configurado; source não controla prompt/provider. Cache input/model/prompt versions. Provider indisponível nunca vira sucesso IA fictício.

- [ ] Escrever os testes discriminantes: test_chunk_offsets_overlap; test_missing_provider_baseline; test_evidence_grounding; test_prompt_injection_data_only; test_model_cache_invalidation; test_invalid_llm_output_rejected.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Cada conceito/summary evidence referencia input válido e saída schema validada.
- [ ] Sem IA, declarar modo baseline e limitar inferências; metadata-only propaga profundidade.
- [ ] Prompt injection não executa tools nem altera estado/publicação/configuração.
- [ ] Mesmo artefacto/config reutiliza output; mudança prompt/model invalida cache; métricas de custo/duração disponíveis.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 7: A07 — Mapear conteúdo e currículo contra snapshot autorizado dos modelos existentes

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/8. **Prioridade:** P1.

**Files:** `facodi_api/services/mapping/service.py`; `facodi_api/services/mapping/snapshot.py`; `facodi_api/services/mapping/ranking.py`; `tests/test_mapping.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A06 (https://github.com/marcelo-m7/facodi-api/issues/7).
- Produces: map_content(document: EnrichedDocument, snapshot: CurriculumSnapshot, scope: str) -> MappingResult.

**Decisões de implementação:** Snapshot company/website/caller, até100 candidatos e top10 por tipo. Retrieval lexical inicial com ranking versionado; courses/slide targets/UCs existentes. Inspecionar facodi.learning.mapping real antes de gravar relações conteúdo-conteúdo. Score de ranking não é probabilidade.

- [ ] Escrever os testes discriminantes: test_only_existing_visible_targets; test_company_website_isolation; test_no_match_is_valid; test_video_without_channel_no_fake_course; test_top10_bound; test_stale_snapshot_invalidated.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Zero IDs/factos académicos inventados; referências invisíveis/de outra company nunca entram no resultado.
- [ ] Relações usam enums existentes, evidence válida, snapshot e versões.
- [ ] Sem matches, lista vazia explícita; vídeo sem channel mantém UC candidate no artefacto até resolução editorial.
- [ ] Mudança do catálogo invalida mapping; ciclos de prerequisite continuam sujeitos às ações de domínio existentes.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 8: A08 — Persistir propostas e integrar revisão/publicação pelos modelos standard existentes

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/9. **Prioridade:** P0.

**Files:** `facodi_api/services/domain_adapter.py`; `facodi_api/models/analysis_job.py`; `facodi_api/tests/test_editorial_handoff.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A04 (https://github.com/marcelo-m7/facodi-api/issues/5), A07 (https://github.com/marcelo-m7/facodi-api/issues/8).
- Produces: persist_proposals(run: PipelineRun, mapping: MappingResult) -> EditorialHandoff; request_publish(run: PipelineRun, reviewer_id: int, expected_revision: int) -> PipelineRun.

**Decisões de implementação:** Reusar facodi.learning analysis job/result, mapping, curriculum coverage e standard slide.channel/slide.slide/tag. Propostas e immutable evidence; Manager decide via actions existentes. Sem create público de analysis result nem write em estados finais. Publicação explícita com recheck no commit.

- [ ] Escrever os testes discriminantes: test_processor_only_output; test_proposals_not_approved; test_manager_review_actions; test_executor_no_publish; test_stale_revision_conflict; test_atomic_publish_replay; test_existing_progress_preserved.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Adapter não duplica submissions/courses/analysis/proposals nem altera reviews aprovados existentes.
- [ ] Executor não publica/aprova; Manager autorizado usa ações com audit fields corretos.
- [ ] Snapshot/visibilidade/revisão alterados bloqueiam publicação até revalidação.
- [ ] Replay de persist/publish tem um efeito ORM; Project Published só após confirmação; conteúdo canónico preserva progresso/anexos.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 9: A09 — Expor endpoints REST JSON assíncronos por capability com bearer obrigatório

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/10. **Prioridade:** P0.

**Files:** `facodi_api/controllers/pipeline.py`; `facodi_api/security/pipeline_security.xml`; `facodi_api/tests/test_pipeline_http.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A01 (https://github.com/marcelo-m7/facodi-api/issues/2), A02 (https://github.com/marcelo-m7/facodi-api/issues/3), A03 (https://github.com/marcelo-m7/facodi-api/issues/4), A04 (https://github.com/marcelo-m7/facodi-api/issues/5), A08 (https://github.com/marcelo-m7/facodi-api/issues/9).
- Produces: POST ingest/enrich/map/pipeline-content -> RunAccepted HTTP202; GET status/artifact -> authorized DTO; POST retry/cancel/publish -> command response.

**Decisões de implementação:** Rotas e erros em contracts.md. type=http com token header explicitamente exigido (evitar fallback de sessão bearer); quotas partilhadas, body limits e Idempotency-Key. Controller não chama YouTube/LLM. API não expõe generic dispatch ou acesso sudo.

- [ ] Escrever os testes discriminantes: test_post_202_no_network; test_session_without_bearer_401; test_invalid_dto_422; test_conflict_409; test_body_413; test_shared_rate_limit; test_artifact_404_for_other_actor; test_publish_manager_only.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Aceite 202 persistido sem rede; status URL/payload corretos; HTTP 409/422/413/429 funcionam.
- [ ] Token ausente com sessão válida ainda é 401; ACLs/grupos company/website/artefactos são aplicados.
- [ ] Portal/submission token não lê run técnico nem obtém task IDs; GET inacessível é404.
- [ ] Todas as operações de comando suportam replay; publicação exige Manager+expected_revision.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 10: A12 — Adicionar provider odoo_python e compatibilidade de cutover sem dois schedulers

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/11. **Prioridade:** P0.

**Files:** `facodi_api/models/analysis_job.py`; `facodi_api/models/res_config_settings.py`; `facodi_api/services/legacy_adapter.py`; `facodi_api/tests/test_provider_cutover.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A03 (https://github.com/marcelo-m7/facodi-api/issues/4), A05 (https://github.com/marcelo-m7/facodi-api/issues/6).
- Produces: _get_provider_registry() -> Mapping[str, Callable]; action_process() -> bool (local enqueue, legacy super); finalize_local_analysis(job, output: ExistingNormalizedAnalysisOutput) -> ExistingAnalysisResult.

**Decisões de implementação:** Herança do ponto de extensão real facodi_learning.analysis.job. Freezar provider por run/job; bridge registry local/legacy. Interceptar action_process para jobs locais, com enqueue único, e preservar super para providers legados. Excluir jobs locais vinculados do cron legado. O runner finaliza output validado sob lock; nenhum marcador queued passa pelo normalizador síncrono. Stripe/Abacate APIs continuam intactas.

- [ ] Escrever os testes discriminantes: test_registry_extension_super; test_no_dependency_cycle; test_legacy_job_provider_frozen; test_local_no_supabase_secret; test_two_crons_one_analysis; test_legacy_provider_regressions.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] facodi_learning/facodi_ai não dependem de API; instalação sem ciclo.
- [ ] Jobs antigos conservam supabase_edge/correlation/history; provider local não exige credencial Supabase.
- [ ] Submissão e analysis job convergem num único run/resultado; dois crons não executam a mesma análise.
- [ ] FacodiApiService/provider registry legados passam regressão; flags/seleção não sobrescrevem provider de run existente.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 11: A10 — Integrar backend e submissões existentes com ações, status seguro e traduções

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/12. **Prioridade:** P1.

**Files:** `facodi_api/models/submission.py`; `facodi_api/views/pipeline_views.xml`; `facodi_api/views/res_config_settings_views.xml`; `facodi_api/i18n/pt_PT.po`; `facodi_api/i18n/es_ES.po`; `facodi_api/i18n/fr_FR.po`; `facodi_api/tests/test_pipeline_ui.py`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A08 (https://github.com/marcelo-m7/facodi-api/issues/9), A09 (https://github.com/marcelo-m7/facodi-api/issues/10), A12 (https://github.com/marcelo-m7/facodi-api/issues/11).
- Produces: action_queue_pipeline() -> PipelineRun; get_safe_submission_pipeline_status(submission) -> SafeStatus.

**Decisões de implementação:** Herança da submissão existente, feature flag, contexto CTA e ligação segura. Backend listas/formulários filtros/tasks/smart buttons; retomar waiting_input via attachment autorizado. Reutilizar tracking/Portal existentes sem novas páginas duplicadas. Inglês source e PO nativos.

- [ ] Escrever os testes discriminantes: test_submission_feature_flag; test_cta_context_preserved; test_safe_status_redacted; test_manual_input_ownership; test_activity_dedup; test_native_translation_catalogues.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Submissão com feature desligada conserva comportamento legado; ligada cria um run com contexto correto.
- [ ] Estado seguro mostra pending/processing/input/review/outcome sem expor artefactos/logs/provider config.
- [ ] Backend pode retry/cancel/open review/publish pelos mesmos serviços; traduções PT/ES/FR preservam contrato.
- [ ] Atividades são deduplicadas e followers portal não são adicionados às tasks técnicas.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 12: A11 — Provar segurança, recuperação, desempenho e observabilidade da pipeline

**Issue:** https://github.com/marcelo-m7/facodi-api/issues/13. **Prioridade:** P1.

**Files:** `tests/test_pipeline_acceptance.py`; `facodi_api/tests/test_pipeline_integration.py`; `scripts/benchmark_pipeline.py`; `docs/facodi-api/execution-security.md`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A05 (https://github.com/marcelo-m7/facodi-api/issues/6), A06 (https://github.com/marcelo-m7/facodi-api/issues/7), A07 (https://github.com/marcelo-m7/facodi-api/issues/8), A08 (https://github.com/marcelo-m7/facodi-api/issues/9), A09 (https://github.com/marcelo-m7/facodi-api/issues/10), A10 (https://github.com/marcelo-m7/facodi-api/issues/12).
- Produces: benchmark(scenarios: Sequence[BenchmarkScenario]) -> BenchmarkReport.

**Decisões de implementação:** Unit/TransactionCase/HttpCase/concurrency com fixtures e offline CI; smoke YouTube opt-in; benchmarks>=30runs, cache hit/miss e stage/network/LLM/ORM separados. Métricas por UUID e retenção com dry-run sem apagar evidência revisada.

- [ ] Escrever os testes discriminantes: test_full_pipeline_offline; test_two_worker_race; test_restart_resume; test_retention_preserves_review; test_no_secrets_in_logs; benchmark cache_hit/cache_miss/provider_unavailable.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Passam fixtures legenda/sem legenda/IP blocked/documento/mapping vazio/LLM inválido/SSRF/cross-company.
- [ ] Dois workers+crash/retry/cancel e replay não duplicam outputs/tarefas/propostas/publicação.
- [ ] Aceite p95<=500ms; normalize<=1s/1MiB; ranking<=2s/100targets; status<=200ms; dequeue<=65s sem backlog, ou relatório bloqueia release e justifica ajuste.
- [ ] Website mantém gate de regressão e consumo de memória/tempo/custo registrado sem segredos.
- [ ] Retenção não remove outputs vinculados a decisões; logs30dias/receipts90dias aplicados com política.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** unitários puros e/ou Odoo tagged tests em base descartável conforme a fronteira alterada. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 13: D01 — Integrar facodi_api, Project e dependências Python na imagem e pins de deploy

**Issue:** https://github.com/marcelo-m7/facodi-deploy/issues/256. **Prioridade:** P0.

**Files:** `addons/facodi-api (gitlink)`; `docker/Dockerfile`; `docker/Dockerfile.dev`; `tests/test_repository_contract.py`; `deploy/coolify/docker-compose.yml`; `docker-compose.dev.yml`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: A04 (https://github.com/marcelo-m7/facodi-api/issues/5), A05 (https://github.com/marcelo-m7/facodi-api/issues/6), A12 (https://github.com/marcelo-m7/facodi-api/issues/11).
- Produces: runtime image -> API lock importable + project/facodi_api installable; source pins -> exact reviewed commits.

**Decisões de implementação:** Atualizar gitlink existente, contrato de módulos/manifests e instalação do lock API no venv Odoo. Preservar Coolify/volumes/migrate/no published ports. Não copiar lógica do addon nem modificar pins de owners sem alteração justificada.

- [ ] Escrever os testes discriminantes: test_repository_contract API gitlink; image import smoke; pip check; bash scripts/validate-repository.sh; compose config.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Imagem importa libs API e executa pip check sem quebrar Odoo/cryptography/pydantic_ai.
- [ ] facodi_api/project instalados via dependências/seleção canónica; manifests/pins exactos validados.
- [ ] Fresh/dev/CI usam o mesmo contrato de dependências e scripts existentes passam.
- [ ] Mudanças de documentação apenas não promovem runtime; integração de código acontece em PR/release próprio.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** checks existentes no runbook deploy, com testes novos indicados na issue. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 14: D02 — Implementar seleção explícita legacy/odoo_python e migração idempotente com cutover

**Issue:** https://github.com/marcelo-m7/facodi-deploy/issues/257. **Prioridade:** P0.

**Files:** `docker/migrate.py`; `deploy/coolify/docker-compose.yml`; `tests/test_facodi_api_migration.py`; `docs/operations.md`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: D01 (https://github.com/marcelo-m7/facodi-deploy/issues/256), A08 (https://github.com/marcelo-m7/facodi-api/issues/9), A10 (https://github.com/marcelo-m7/facodi-api/issues/12).
- Produces: configure_processing_plane(config, database) -> persisted explicit provider; enabled flag -> new local intake gate.

**Decisões de implementação:** Implementar FACODI_PIPELINE_ENABLED/FACODI_PIPELINE_PROVIDER; legacy mantém par Supabase; local não é sobrescrito pela ausência/presença de secrets. Fresh/upgrade sem I/O externo; projeto idempotente. Inventário/drain de legado e backup emparelhado antes de rollout.

- [ ] Escrever os testes discriminantes: test_default_legacy; test_partial_supabase_pair_fails; test_local_selection_persists; test_double_upgrade_no_duplicates; test_upgrade_no_network; test_rollback_history_preserved.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Ausência de novos flags preserva legacy e fail-closed do par Supabase.
- [ ] Provider local exige addon/deps e continua local num segundo migrate independentemente de secrets legados.
- [ ] Nenhum upgrade reanalisa/publica dados reais ou altera approved reviews.
- [ ] Rollback de configuração pausa intake novo e mantém runs/artefactos; schema rollback exige backup DB+filestore.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** checks existentes no runbook deploy, com testes novos indicados na issue. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

### Task 15: D03 — Provar pipeline integrada em staging e preparar release, backup e recuperação

**Issue:** https://github.com/marcelo-m7/facodi-deploy/issues/258. **Prioridade:** P0.

**Files:** `tests/test_facodi_api_runtime.sh`; `tests/test_coolify_runtime.sh`; `tests/test_paired_backup_restore.sh`; `.github/workflows/ci.yml`; `docs/operations.md`. Ficheiros existentes são modificados; os restantes são criados no owner indicado. Atualizar __init__.py/__manifest__.py quando o novo ficheiro for carregado pelo addon.

**Interfaces:**
- Consumes: D02 (https://github.com/marcelo-m7/facodi-deploy/issues/257), A11 (https://github.com/marcelo-m7/facodi-api/issues/13).
- Produces: release evidence -> exact SHA/pins/image + fresh/upgrade/replay/restore/benchmark proofs.

**Decisões de implementação:** CI descartável com fixture completa e browser/backend/Project/status; staging YouTube opt-in, runtime cron observado, falhas/replay/restores. Preparar release separado; usar issue #224/PR #226 para build prebuilt quando aprovados, sem duplicar ou trocar Compose sem prova Coolify.

- [ ] Escrever os testes discriminantes: bash tests/test_coolify_runtime.sh; bash tests/test_facodi_api_runtime.sh; paired backup restore; exact-head CI; non-production Coolify acceptance.
- [ ] Executar só os testes novos para confirmar falha pelo comportamento ausente, não por ambiente mal configurado.
- [ ] Implementar interface e limites acima, preservando contratos anteriores.
- [ ] Executar novamente testes novos e regressões do owner; exigir todos os critérios seguintes.
- [ ] Fresh+upgrade+segundo upgrade e pipeline até publicação descartável passam com Manager explícito.
- [ ] Restore emparelhado conserva Website Builder, progresso, attachments e evidência/project tasks.
- [ ] Benchmark/gates de API e Website passam; logs e proof sanitizados publicados no PR.
- [ ] Produção só promovida depois de evidência e release explícito; sem promessa zero downtime e sem recriar volumes.
- [ ] Atualizar docs/DTOs afetados, anexar evidência e fazer commit focado no owner; abrir PR ligado à issue.

**Verificação:** checks existentes no runbook deploy, com testes novos indicados na issue. Resultado esperado: testes relevantes passam, sem output privado; benchmark/live-network exigem relatório real quando aplicável.

## Handoff e integração

A aceitação end-to-end pertence a D03, não aos mocks unitários. Entrega documental está em PR separado de implementação. O primeiro PR de código recomendado cobre A01 e/ou A02 sem ativar engine local. Antes de executar código, rever o desenho e o plano; executar pelo método acordado na conversa. Esta entrega não escolhe nem inicia delegação, não faz merge e não toca produção.
