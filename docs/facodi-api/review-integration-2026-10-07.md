# Revisão e integração — 7 de outubro de 2026

**Base isolada corrigida e mesclada; integração ampla ainda pendente.** [API PR #16](https://github.com/marcelo-m7/facodi-api/pull/16) e [deploy PR #261](https://github.com/marcelo-m7/facodi-deploy/pull/261) passaram pelos gates finais. MCP confirmou a versão 19.0.2.0.0 e publicação/replay de conteúdo original em curso privado. Aquisição real de dois vídeos falhou com `YOUTUBE_IP_BLOCKED`; não declarar E2E YouTube concluído.

## Revisões finais

- Source API: `3f2683bf0dff7c7975e0037db776f4227dede796`; merge em main: `4f9051ff78469fb8acab6891b3eff5ad21b71a05`.
- Source deploy: `5685788e8a49d9870becac0172cd82462accddc8`; merge: `2dc03d9da929d573388365366d15f6230976c626`.
- O deploy fixa exatamente o source API acima. Commits apenas documentais posteriores não alteram o código desse pin.

## Correções incorporadas

- Guards ORM/create/write/default context, owner/company/website scope, privileged cron, worker locks and authorization failures.
- Odoo19 HTTP supported wrapper get_data, route limit before parameter parsing, bounded 262144 bytes + sentinel, real chunked/keepalive/concurrent tests.
- Legacy19.0.1 upgrade preserves metadata/source/status, quarantines unverifiable history, disables gate/cron and retires broad ACLs.
- YouTube child transport timeout45s, response/segment/text limits, early redirect rejection, sanitized error codes; manual text explicitly distinguished.
- Canonical external video keeps video URL with summary in description, draft native content review requires reviewer-supplied provenance evidence, atomic guarded publication.
- Scoped legacy Supabase export suppression on v2 creation; default context scrub prevents injected jobs/reviews; ordinary legacy hooks preserved.
- Production/dev/test same immutable Odoo base, runtime dependencies installed/pipcheck, API module migrate and persistent storage in existing Odoo volume.
- Full isolated CI includes native permissions, install/upgrades, actual HTTP/scheduler, publication and restart; full platform includes native governance/legacy isolation, Website/browser, paired disposable backup/restore.

O HTTP usa `get_data(cache=False)` suportado pelo wrapper Odoo 19, limite antes do parsing e sentinela de 262145 bytes para um payload máximo de 262144. Locks, owner/company/website, defaults hostis, owner inválido no início da fila e migração real do legado têm testes em Odoo nativo.

Quando Learning está instalado, aprovação exige eLearning Manager e `publication_evidence` com author, rights_mode (original/licensed/external), usage_basis e purpose. Cria draft, chama `facodi.learning.content.review.action_approve` e só então publica pelo guard nativo, sob savepoint. Vídeo usa URL externa com resumo em description. A contenção do export legado cobre criação v2; futuras edições precisam de política de origem/provider persistidos.

## Evidência

- [CI API 37609607055](https://github.com/marcelo-m7/facodi-api/actions/runs/37609607055): SUCCESS, 57 passed / 1 skip apenas da suíte que exige Odoo.
- [Runtime final 37610480117](https://github.com/marcelo-m7/facodi-deploy/actions/runs/37610480117): SUCCESS, 9 testes ORM nativos, clean install, upgrade 19.0.1, upgrade repetido, HTTP, scheduler real, publicação e restart.
- [Plataforma final 37610480249](https://github.com/marcelo-m7/facodi-deploy/actions/runs/37610480249): SUCCESS, governança API+Learning, preservação dos hooks legados, Website/browser e restore DB+filestore descartável.
- Após merge: [runtime main 37611311972](https://github.com/marcelo-m7/facodi-deploy/actions/runs/37611311972) e [plataforma main 37611312267](https://github.com/marcelo-m7/facodi-deploy/actions/runs/37611312267), ambos SUCCESS.

MCP em facodi.com/database facodi: runs 4/5 de YouTube sem transcript manual falharam YOUTUBE_IP_BLOCKED e não publicaram. Run 6 com texto original passou waiting_review/publicação, review nativo 553 approved, slide 1062 no curso privado 43; replay manteve o mesmo slide/review. Projetos 3/4/5 followers-private e três subtarefas por run. Intake com gate desligado foi recusado sem run.

Configuração final confirmada: pipeline_enabled=false, cron26 inactive, grupos temporários removidos, revisão editorial Website mantida, curso43 members/invite/unpublished. Histórico1/2/3 ficou quarantined/cancelled com legacy_status preservado, sem reprocessamento.

## Limites e continuação

Baseline determinístico não é LLM independente nem alinhamento curricular oficial. Capabilities/OpenAPI, attachment documental, retry/cancel/waiting_input/lease, handoff curricular e integração dos consumidores ainda faltam. Não fechar as epics apenas pelos testes da base. Cutover amplo permanece desligado.

Restore aprovado foi descartável; backup produtivo e SHA da imagem produtiva não foram verificados. MCP comprovou dados/versão/publicação por ORM; HTTP Website foi comprovado no CI, não por browser produtivo.

[Relatório operacional completo](https://github.com/marcelo-m7/facodi-deploy/blob/main/docs/facodi-api/acceptance-2026-10-07.md) · [Prompt integral da próxima fase](https://github.com/marcelo-m7/facodi-deploy/blob/main/docs/facodi-api/prompt-platform-integration.md). A próxima fase resolve aquisição YouTube, integra os consumidores e simplifica Learning/AI preservando domínio, revisão e histórico.
