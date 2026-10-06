# Execução, segurança, performance e operação

## Runner standard

Lógica Python dentro do addon; execução por `ir.cron`, nunca em controller HTTP. Tick inicial 1 minuto, concorrência 1, limite de lote 1 etapa, orçamento de chamada limitado pelo tempo restante do cron. `_commit_progress` somente no contexto de cron, retornando quando não resta orçamento. Uma chamada provider tem connect timeout 3 s, read timeout 10 s e deadline total 20 s por tentativa, incluindo redirects/retries internos. Converter roda com hard timeout 20 s. Ajustar para limites efetivos do worker medidos em staging; estes valores são configuração inicial proposta.

Odoo recomenda batches de poucos segundos. Sempre que uma etapa ultrapassar o orçamento restante, não a iniciar; chunkar enriquecimento em checkpoints internos e reportar progresso. Chamadas de rede podem demorar mais do que esse alvo: benchmark é gate para aceitar o cron ou justificar um executor dedicado que execute o mesmo código do addon. Requests timeout não é deadline total: enforcement via executor limitado/subprocesso, cuja saída é DTO JSON, sem `env` nem cursor herdado. Não criar threads permanentes ou compartilhar Environment com threads/processos. O worker abre/usa o seu próprio contexto ORM após terminar a operação externa.

Cron no primeiro release implica espera de fila de até cerca de 60 segundos sem carga. Meta de dequeue p95 <=65 s em staging sem backlog. Não prometer início subsegundo; notificações/queue wakeup só entram por decisão medida posterior.

O job existente chama `action_process()` e espera provider síncrono normalizado. A herança API intercepta `action_process()` somente para jobs `odoo_python`, cria/localiza o run único e devolve o controlo sem chamar `super()` para esses jobs; para providers legados continua `super()` no subconjunto correspondente. O cron legado exclui jobs locais já vinculados ao runner, evitando marcá-los como novas tentativas a cada tick. O runner é o único dono das etapas locais e finaliza o job através de método processor privado que valida estado, lock, actor e provenance. Nunca devolver `{queued: true}` ao normalizador legado como se fosse analysis result. Registry local serve apenas adapter de output concluído; não é um mecanismo de scheduling.

## Idempotência e concorrência

Identidade de comando: `(company, actor, capability, Idempotency-Key)`, com unique SQL. Hash canónico de JSON já validado inclui versão do pipeline/profile, contexto e identidade do artefacto. Mesma key/hash devolve mesmo run; conflito é 409. Retenção da identidade 90 dias; documentar que replay fora desta janela já não é garantido. `publish`, `retry`, `cancel` também têm command receipt persistido no run com unique separado; não substituir a idempotência original.

Constraint `(run_id, step_key)` evita subtarefas/steps duplicados. Processamento at-least-once com efeitos idempotentes, não promessa de exactly-once na rede. M1: claim/lock transacional, uma etapa curta de cada vez e side effects ORM no mesmo commit. Provar dois workers a disputar o mesmo step; rollback/crash libera lock e reprocessa sem duplicar efeitos. Não implementar lease commitado sem token de fencing. Se for necessário libertar lock durante I/O, o incremento exige lease expiring + generation e validação no commit; um worker antigo nunca pode sobrepor resultado novo.

Cancelamento entre etapas é imediato; uma etapa já em I/O só termina/interrompe no deadline. Após cancelar, revalidar sob lock antes de persistir/publicar. Retry reinicia só falha e descendentes invalidados; reutiliza artefactos predecessores íntegros. Tentativas append-only com correlation/duração/erro sanitizado. Se o modelo existente `analysis.attempt` cobre uma operação, ligá-lo ao step em vez de replicar a mesma tentativa.

## Falhas

| Classe | Código seguro | Comportamento |
| --- | --- | --- |
| timeout/429/5xx temporário | `provider_temporary` | máximo 3 tentativas totais; espera 60/180 s com jitter até 20%, sem sleep no worker |
| IP bloqueado | `transcript_blocked` | waiting_input; não repetir continuamente |
| legenda ausente / vídeo removido | `transcript_missing` / `source_unavailable` | pendência/intervenção ou falha terminal; não inventar conteúdo |
| ficheiro >limite / tipo não suportado | `source_too_large` / `unsupported_format` | falha controlada sem conversão |
| schema LLM inválido / evidence inexistente | `invalid_analysis_output` | uma nova tentativa dentro do máximo 3; output inválido não persiste como análise válida |
| alvo já não autorizado | `target_unavailable` | re-map/revisão obrigatória, nunca sudo para publicar |
| dependência falhou | `blocked_dependency` | impedir descendentes; manter causa original |

Retry budget único evita 3 retries MarkItDown multiplicados por 3 retries runner. Desativar/restringir retry interno, ou contabilizar todas as chamadas no budget. Honrar Retry-After bounded ao schedule configurado. Depois do máximo: Failed + uma atividade de triagem.

## Segurança por fronteira

- API: token obrigatório, grupo Operator, company/website e actor registados pelo servidor; inputs rejeitam campos reservados.
- Intake existente: o Portal cria a submissão pelas regras atuais; hook autorizado de processamento enfileira em nome do executor configurado e conserva o submitted_by original na submissão. O utilizador Portal não ganha grupo Operator nem token. Revalidar contexto CTA na política de intake antes de aproveitar privilégios do executor; nunca transformar um ID inacessível enviado pelo Portal em alvo legível por sudo.
- Project/artefactos: ACL privadas, attachments sem `public`, checks de ownership em `/web/content`; token de submissão não dá acesso ao job técnico.
- Rede: YouTube allowlist de HTTPS/443; documentos M1 somente attachments autorizados. Rejeitar credenciais em URL, file/data/ftp, IP literal privado, loopback, metadata cloud, portas arbitrárias.
- Fetch: resolver A/AAAA, rejeitar todos os IPs não públicos, revalidar cada redirect (máximo 3) e fixar conexão ao IP validado preservando TLS hostname; prevenção de DNS rebinding não se resolve apenas analisando o hostname. Converter não faz fetch livre.
- Limites: attachment/fetch 10 MiB; Markdown 2 MiB UTF-8; até 10 000 segmentos; chunks 4 000 chars com overlap 200 e máximo 200 chunks; 100 candidatos pré-ranking e 10 finais por tipo. Documento acima do limite pede divisão; não truncar silenciosamente.
- IA: conteúdo/transcrição é dado não confiável; prompt injection não executa tools/SQL, não muda system prompt, URLs ou estado editorial; referências de evidência são revalidadas.
- Segredos: só configuração write-only/resolução existente; stdout/stderr do conversor limitado e sanitizado; nunca body bruto de erro em chatter.
- Webhooks: exigir secret e assinatura; validar bytes originais antes de parse, timestamp/TTL quando disponível e event ID unique; Stripe usa verificador oficial com signing secret. Sem secret desativar a rota (503) e não criar eventos. Eventos de pagamentos não publicam conteúdos.

Limites de API iniciais: 30 comandos/min por utilizador técnico, máximo 5 runs ativos por utilizador, máximo 100 runs pendentes globais; responder 429 quando excedido. Rate limits só em memória não servem com múltiplos workers: enforcement partilhado pela base/config de proxy com teste de concorrência. Operações de leitura até 120/min; polling recomendado 5–15 s com backoff.

## Cache e performance

Cache de artefactos keyed por source identity + input hash + idioma + adapter version + pipeline version. Enrichment inclui modelo/prompt/settings; mapping inclui snapshot do catálogo/ranking. Cache nunca bypassa autorização. Transcrição cacheada por 24 h antes de revalidar; demais saídas imutáveis reutilizadas quando inputs/version forem iguais. Catálogo revisto invalida só mapping.

Metas propostas, não resultados medidos: aceite POST p95 <=500 ms sem rede; normalização local de Markdown <=1 MiB p95 <=1 s; ranking lexical de até 100 candidatos p95 <=2 s; consulta status p95 <=200 ms. Medir hardware/carga/image/Python, amostra >=30 runs por cenário e separar tempo de fila, rede, LLM, conversão e ORM. Primeiro baseline sem LLM; comparativo cache hit/miss; monitorar memória e responsividade Website com pipeline ativa.

Observabilidade: UUID run/request, step, attempt, cache hit, timestamps/duração, versão, provider/model e custo reportado; métricas de pendentes, oldest queued, falhas, espera humana e consumo. Emitir logs structured sem conteúdo privado; chatter somente transições. Uma falha não vira `health=down` público automaticamente; alertar equipa pela atividade Project, sem expor números internos no health público.

Retenção inicial: logs detalhados seguros 30 dias; receipts de idempotência 90 dias; evidência usada em decisão editorial mantida enquanto existir conteúdo/decisão vinculada. Limpeza só de artefactos órfãos não referenciados após 90 dias, com check de FK e dry-run; nunca apagar analysis result/review aprovado imutável. Pedido de remoção de dados segue processo de retenção/restrição de acesso, não cron que remove histórico aprovado.

## Gate de testes

Unitários offline dos DTOs/adapters/ranking; testes Odoo `TransactionCase` para constraints/Project/domain actions; `HttpCase` para token/HTTP/ACL; subprocessos/fetch mockados; concorrência real com dois cursors para claims e replay; fresh/upgrade/restart/backup restore no deploy. Live YouTube é smoke opt-in em staging, pois bloqueios externos não devem tornar unit tests flakey. Não usar aprovações de produção como fixture.
