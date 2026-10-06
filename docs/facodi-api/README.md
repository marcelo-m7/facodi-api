# FACODI API — proposta de desenvolvimento

Data: 2026-10-06. Estado: proposta pronta para desenvolvimento; funcionalidades descritas ainda não implementadas. Esta entrega cria documentação e backlog, sem mudar processamento, dados, pins ou produção.

## Objetivo

Receber um conteúdo, ingerir texto e transcrição, enriquecer com evidência, mapear contra cursos e currículos existentes e submeter os resultados a revisão humana. Tudo em Python num único addon `facodi_api`, com endpoints por capability e uma representação operacional em Odoo Project standard.

A arquitetura proposta substitui, para novos runs explicitamente selecionados, a obrigação anterior de executar análise exclusivamente em Supabase Edge Functions. A seleção e o cutover são decisões de release: escrever esta proposta não altera o provider ativo.

## Ler nesta ordem

1. [Especificação completa](../superpowers/specs/2026-10-06-facodi-api-design.md): escopo, arquitetura, alternativas e decisões.
2. [Objetos e contrato HTTP](contracts.md): DTOs, endpoints, estados e exemplos.
3. [Odoo Project](odoo-project.md): tarefa por execução, subtarefas e revisão.
4. [Bibliotecas e evidência](libraries.md): MarkItDown, transcrições, limitações e dependências.
5. [Execução, segurança e desempenho](execution-security.md): cron, retries, SSRF, idempotência e métricas.
6. [Plano de implementação](../superpowers/plans/2026-10-06-facodi-api.md): tarefas com interfaces, ficheiros e validação.
7. [Backlog ligado](backlog.md): issues, prioridades, dependências e milestones propostos.
8. [Integração e rollout](https://github.com/marcelo-m7/facodi-deploy/tree/docs/facodi-api-proposal-20261006/docs/facodi-api): plano no repositório de deploy.

## Primeiro resultado verificável

Uma URL YouTube com legenda disponível gera um run e uma tarefa privada; ingestão produz Markdown e segmentos; enriquecimento identifica conceitos com referências aos segmentos; mapping sugere apenas alvos existentes; o Manager aprova pelas ações de domínio existentes; a publicação explícita reutiliza `slide.channel`/`slide.slide`. Repetir a requisição não duplica tarefas, conteúdos nem relações aprovadas.

Sem legenda: o utilizador vê uma pendência concreta e pode fornecer transcrição. Markdown com título/descrição apenas não equivale a vídeo analisado. Nenhuma etapa automática concede ECTS, equivalência académica ou publicação.

## Limites desta entrega

Odoo 19 Community; sem Studio, dependência Enterprise, FFI, Rust, FastAPI ou serviço serverless obrigatório. O projeto operacional existe no desenho e será criado pela implementação do addon; não foi criado num Odoo vivo nesta entrega. Issues GitHub acompanham engenharia e não são as tarefas operacionais por conteúdo.
