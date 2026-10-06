# Backlog de implementação — FACODI API

Estado: planeado; checkboxes não representam execução. Epic do addon: https://github.com/marcelo-m7/facodi-api/issues/1. Epic de integração: https://github.com/marcelo-m7/facodi-deploy/issues/255.

## Issues, prioridades e dependências

| Issue | Prioridade | Entrega | Bloqueada por |
| --- | --- | --- | --- |
| [A01](https://github.com/marcelo-m7/facodi-api/issues/2) | P0 | Reforçar autenticação, idempotência e isolamento dos webhooks existentes | — |
| [A02](https://github.com/marcelo-m7/facodi-api/issues/3) | P0 | Definir DTOs tipados e validação dos contratos ingest/enrich/map/pipeline v1 | — |
| [A03](https://github.com/marcelo-m7/facodi-api/issues/4) | P0 | Implementar runs, etapas e artefactos imutáveis com runner cron recuperável | [A02](https://github.com/marcelo-m7/facodi-api/issues/3) |
| [A04](https://github.com/marcelo-m7/facodi-api/issues/5) | P0 | Espelhar cada execução em Project standard com tarefas, subtarefas e dependências | [A03](https://github.com/marcelo-m7/facodi-api/issues/4) |
| [A05](https://github.com/marcelo-m7/facodi-api/issues/6) | P0 | Ingerir YouTube com MarkItDown e transcrição temporal por adapter seguro | [A02](https://github.com/marcelo-m7/facodi-api/issues/3), [A03](https://github.com/marcelo-m7/facodi-api/issues/4) |
| [A06](https://github.com/marcelo-m7/facodi-api/issues/7) | P1 | Enriquecer Markdown com chunks e conceitos rastreáveis via facodi_ai | [A05](https://github.com/marcelo-m7/facodi-api/issues/6) |
| [A07](https://github.com/marcelo-m7/facodi-api/issues/8) | P1 | Mapear conteúdo e currículo contra snapshot autorizado dos modelos existentes | [A06](https://github.com/marcelo-m7/facodi-api/issues/7) |
| [A08](https://github.com/marcelo-m7/facodi-api/issues/9) | P0 | Persistir propostas e integrar revisão/publicação pelos modelos standard existentes | [A04](https://github.com/marcelo-m7/facodi-api/issues/5), [A07](https://github.com/marcelo-m7/facodi-api/issues/8) |
| [A09](https://github.com/marcelo-m7/facodi-api/issues/10) | P0 | Expor endpoints REST JSON assíncronos por capability com bearer obrigatório | [A01](https://github.com/marcelo-m7/facodi-api/issues/2), [A02](https://github.com/marcelo-m7/facodi-api/issues/3), [A03](https://github.com/marcelo-m7/facodi-api/issues/4), [A04](https://github.com/marcelo-m7/facodi-api/issues/5), [A08](https://github.com/marcelo-m7/facodi-api/issues/9) |
| [A10](https://github.com/marcelo-m7/facodi-api/issues/12) | P1 | Integrar backend e submissões existentes com ações, status seguro e traduções | [A08](https://github.com/marcelo-m7/facodi-api/issues/9), [A09](https://github.com/marcelo-m7/facodi-api/issues/10), [A12](https://github.com/marcelo-m7/facodi-api/issues/11) |
| [A11](https://github.com/marcelo-m7/facodi-api/issues/13) | P1 | Provar segurança, recuperação, desempenho e observabilidade da pipeline | [A05](https://github.com/marcelo-m7/facodi-api/issues/6), [A06](https://github.com/marcelo-m7/facodi-api/issues/7), [A07](https://github.com/marcelo-m7/facodi-api/issues/8), [A08](https://github.com/marcelo-m7/facodi-api/issues/9), [A09](https://github.com/marcelo-m7/facodi-api/issues/10), [A10](https://github.com/marcelo-m7/facodi-api/issues/12) |
| [A12](https://github.com/marcelo-m7/facodi-api/issues/11) | P0 | Adicionar provider odoo_python e compatibilidade de cutover sem dois schedulers | [A03](https://github.com/marcelo-m7/facodi-api/issues/4), [A05](https://github.com/marcelo-m7/facodi-api/issues/6) |
| [D01](https://github.com/marcelo-m7/facodi-deploy/issues/256) | P0 | Integrar facodi_api, Project e dependências Python na imagem e pins de deploy | [A04](https://github.com/marcelo-m7/facodi-api/issues/5), [A05](https://github.com/marcelo-m7/facodi-api/issues/6), [A12](https://github.com/marcelo-m7/facodi-api/issues/11) |
| [D02](https://github.com/marcelo-m7/facodi-deploy/issues/257) | P0 | Implementar seleção explícita legacy/odoo_python e migração idempotente com cutover | [D01](https://github.com/marcelo-m7/facodi-deploy/issues/256), [A08](https://github.com/marcelo-m7/facodi-api/issues/9), [A10](https://github.com/marcelo-m7/facodi-api/issues/12) |
| [D03](https://github.com/marcelo-m7/facodi-deploy/issues/258) | P0 | Provar pipeline integrada em staging e preparar release, backup e recuperação | [D02](https://github.com/marcelo-m7/facodi-deploy/issues/257), [A11](https://github.com/marcelo-m7/facodi-api/issues/13) |

## Milestones propostos

| Milestone | Resultado | Gate |
| --- | --- | --- |
| M1 — Ingestão operacional | ingestão/transcrição, run/tasks e provider local com endpoint ingest básico | A01–A05, A12 e fatia ingest de A09 validados offline |
| M2 — Inteligência e mapping | enrichment com evidência, PDF/DOCX e sugestões de alvos reais | A06–A08 e adapter documental A05; revisão humana comprovada |
| M3 — API e release integrado | capabilities completas, backend/submissões, migração, recuperação e benchmarks | A09–A11 e D01–D03 concluídas com CI/staging |

São milestones de produto propostos, não objetos milestone GitHub criados. A fatia ingest de A09 pode ser entregue em M1 antes das restantes rotas; a issue A09 só fecha quando todo o contrato passa. Não usar avanço de milestone para contornar dependências de publicação.

## Ordem recomendada

A01 e A02 podem ser desenvolvidos independentemente. Sequência de contratos: A03, A04/A05, A12, A06, A07, A08, A09, A10, A11. D01 começa após dependências API; D02 segue integração editorial; D03 exige aceitação do addon. Prioridade P0 é gate de release, não necessariamente ordem cronológica.

## Definition of Done

- Critérios da issue têm teste/evidência relevante no PR do owner.
- Interfaces/DTOs/documentação continuam consistentes; segredos e dados privados ausentes.
- Code review e CI do commit efetivo passam; network smoke real é distinguido de fixture.
- Deploy recebe SHA revisto por gitlink; nenhum conteúdo publicado automaticamente.
- Release não apaga histórico/progresso/filestore nem dispensa revisão Manager.

## Próximo incremento concreto

Começar por [A01](https://github.com/marcelo-m7/facodi-api/issues/2) e [A02](https://github.com/marcelo-m7/facodi-api/issues/3): fechar autenticação das superfícies existentes e contratos tipados. Em seguida [A03](https://github.com/marcelo-m7/facodi-api/issues/4) fornece a base transacional usada por todas as funções. Esta documentação não implementa essas issues.

