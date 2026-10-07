# Prompt para o agente local — concluir FACODI API e comprovar E2E isolado

Você é responsável por concluir a implementação da FACODI API e entregar evidências reproduzíveis de funcionamento ponta a ponta. Trabalhe autonomamente: investigue, implemente, teste, corrija falhas, atualize documentação/issues e prepare PRs. Não encerre com plano, smoke test ou declaração genérica. Só declare conclusão quando todos os critérios obrigatórios abaixo passarem no commit final. Se faltar acesso ou recurso indispensável, documente o bloqueio concreto e o que foi tentado; não invente evidência nem contorne isolamento.

## 1. Contexto e fontes

Repositórios: https://github.com/marcelo-m7/facodi-api e https://github.com/marcelo-m7/facodi-deploy.

Auditoria/correções: API PR #15, deploy PR #260; relatório docs/facodi-api/audit-2026-10-07.md. Backlog: API #1–#13 e deploy #255–#258. Leia AGENTS.md aplicáveis, docs e discussões/reviews atualizados. Use instruções atuais de isolamento acima de propostas antigas de cutover ou dependência de facodi-ai.

Estado observado em 07/10/2026: API main d7c7579, deploy main 8ddc65e; PRs de auditoria abertos. Confirme novamente, pois os branches podem mudar. A auditoria contou 50 testes offline no branch de contenção; isso NÃO prova HTTP/ORM/Odoo nem conclusão da API. O relatório anterior registra instalação e testes em produção: não repetir esse procedimento.

## 2. Isolamento obrigatório

- Crie branch/worktree ou clone separado. Preserve alterações locais de outros trabalhos. Não faça push em main, merge de produção, alteração de pin em main ou acionamento do Coolify.
- Não conecte a facodi.com, marcelo-m7.me, edu-open2.odoo.com nem às conexões codoo.facodi/connect_facodi para instalar, escrever, testar ou aprovar conteúdo. Não reutilize banco, filestore, volumes, filas, rede, segredos ou chaves da instância atual.
- Crie ambiente descartável próprio: Odoo 19 Community, PostgreSQL, projeto Compose exclusivo, nomes exclusivos, portas vinculadas a 127.0.0.1 e diretórios/volumes próprios. Use fixtures sintéticas e segredos efêmeros. E-mails e notificações externas devem estar desativados; somente comunicação interna de teste.
- O harness deve recusar por padrão qualquer host/banco fora de sua allowlist de teste, checar nomes/labels dos recursos e demonstrar que não depende de credenciais de produção. Limpeza remove somente recursos identificados como pertencentes ao harness; nunca docker system prune, remoção global ou down -v de outro projeto.
- Pipeline novo e cron desativados por padrão; ativação explícita apenas no ambiente descartável. Nenhum novo hook/callback deve interceptar o processing atual. Simplificar facodi-learning e remover chamadas facodi-ai são fase futura, fora desta entrega.
- O PR #260 não é um rollback de banco. Não aplicar pin antigo a uma instância com addon instalado; tratar qualquer recuperação operacional em proposta separada com inventário, backup e aprovação específica.

## 3. Conciliar as correções antes de avançar

Atualize refs, confira todos os commits e resolva conflitos no branch isolado. Incorpore as correções do PR #15 sem perder melhorias válidas do agente: bearer nativo, gate, cron inativo, publicação incompleta bloqueada, parser limitado, hashes, replay, armazenamento, YouTube e retornos XML-RPC. Não reintroduza auth public/fail-open, sudo sobre execuções, fallback JSON inválido para {}, sync na rota assíncrona nem exposição de str(exc).

Leia e trate todos os reviews. A proteção de replay antigo atualmente bloqueia reprocessamento até migração: implemente migração explícita verificável ou preserve esse erro documentado; nunca considere cache sem fingerprint como prova de equivalência. Exclua timestamps voláteis do fingerprint e inclua snapshot estável, escopo, versão da pipeline e configuração não secreta do provider. Não sobrescreva trabalho concorrente nem faça force push em branches compartilhados.

## 4. Concluir as capacidades reais da API

- Engine Python independente de Odoo/facodi-ai: DTOs com validação, ingestão, normalização, enriquecimento, mapeamento e execução por etapa/CLI. Documentar contrato OpenAPI versionado, payloads, limites, erros e compatibilidade.
- Ingestão de Markdown/TXT/PDF/DOCX e YouTube: arquivos reais de teste, tipo/tamanho/URL validados, proteção de SSRF e ZIP bombs quando aplicável, transcrição com timings de origem; sem inventar tempos nem concluir sucesso com conteúdo vazio. Aquisição bloqueada exige erro recuperável/fallback explícito.
- Provider independente de facodi-ai com saída estruturada validada, provenance/evidências por chunk, timeout, budget, retry controlado e redaction. Baseline determinístico deve ser identificado como baseline, não como IA real.
- Catálogo autorizado de cursos/UC dos modelos já existentes, sem limite silencioso de 50 entradas; snapshot estável por escopo e mapping com evidências, ranking e confiança explicada, sem confundir score lexical com probabilidade calibrada.
- Persistência durável e separada: runs, etapas, artefatos, versões, input/provider/catalog hashes, retenção e recuperação. Garantir lock/claim concorrente, checkpoint, retries idempotentes, cancelamento e deadlines. Não usar /tmp como única persistência durável.
- HTTP assíncrono: submissão 202 sem processar na request, status/artefatos, capacidades previstas, retry/cancelamento e revisão. Bearer nativo, grupos de operador/revisor, ownership e empresa, ACL/record rules sem sudo global. Idempotency-Key no escopo certo; mesmo payload retorna a execução, payload diferente retorna 409, concorrência não retorna 500 nem duplica.
- JSON estrito: 400/422 conforme contrato, 401/403 para autenticação/permissão, 404 para recurso não visível, 413 para excesso inclusive sem Content-Length, 415 para mídia inadequada; gate desativado deve recusar execução. Logs não expõem tokens, transcrições privadas ou segredos de providers.
- Project standard: projeto privado por escopo, tarefa criada desde submissão, subtarefas por etapa, dependências, falhas/retries sincronizados, HTML escapado e chatter autorizado. Não mudar objetos/campos do legado para acomodar o novo pipeline.
- Revisão/publicação real: revisor inspeciona/edita/recusa/aprova proposta; aprovação cria/atualiza conteúdo no alvo autorizado e persiste vínculos/artefatos. Publicação transacional e idempotente, sem conteúdo antes da aprovação. Status published somente após verificação do conteúdo real e audit trail. Remova o bloqueio 501 apenas quando esse adapter estiver implementado/testado. Repetir aprovação não duplica conteúdo, tags ou relações.

## 5. Ambiente reproduzível e instalação

Entregue configuração e comandos no repositório que criem tudo desde checkout limpo. Defina dependências/lock e pins, health checks, preparação de banco, instalação e upgrade do addon. Se Docker estiver indisponível, use alternativa local isolada com Odoo/PostgreSQL reais; não troque testes de integração por mocks. Instalação de dependências no workspace é autorizada, sem modificar serviços existentes.

Teste tanto instalação limpa quanto upgrade de uma fixture descartável representando a versão anterior. Inclua schemas/constraints compatíveis com Odoo 19. Verifique que instalar/atualizar mantém gate e cron desligados e não inicia processing legado. Registre SHAs e versões realmente usados; não use upstream flutuante como evidência reproduzível.

## 6. E2E obrigatório por HTTP e worker reais

Implemente um comando orquestrador documentado (por exemplo make e2e-isolated) que prepare o ambiente, instale, execute testes, produza relatório e retorne código !=0 para falha/bloqueio. Defina os comandos reais, não apenas exemplos.

O fluxo positivo deve:
1. Gerar API keys efêmeras de operador e revisor nos usuários de teste.
2. Enviar conteúdo por HTTP com chave de idempotência e obter 202/run_id. Provar que o enriquecimento não rodou na request.
3. Deixar o cron/worker real consumir a execução; polling com prazo limitado até waiting_review, sem chamar action_execute_pipeline manualmente para substituir a fila.
4. Conferir artefatos, evidências e mapping contra fixture de catálogo, e projeto/tarefa/subtarefas privadas sincronizadas.
5. Demonstrar que o conteúdo ainda não foi publicado.
6. Editar/aprovar pela interface HTTP de revisão, como revisor autorizado.
7. Conferir no ORM E pela leitura HTTP/website do ambiente que conteúdo real existe no curso/UC correto com vínculos/tags esperados. Assertar dados concretos, não apenas published/chatter/health 200.
8. Repetir submissão e aprovação, conferindo IDs e contagens inalterados; divergência de payload deve gerar 409.
9. Reiniciar worker e Odoo usando o mesmo volume de teste e comprovar persistência/consulta/replay sem novo processamento indevido.

Não mockar HTTP controller, Odoo ORM, PostgreSQL, worker, fila ou publication adapter neste E2E. Fixtures/mock server somente nas fronteiras externas YouTube/LLM para determinismo, claramente identificadas. Não chamar isso de prova de aquisição/IA real.

## 7. Matriz de aceite que deve passar

| Área | Prova exigida |
| --- | --- |
| Instalação/upgrade | Odoo real, migrations/constraints/registro de rotas; gate e cron inicialmente inativos |
| Segurança | Sem token, token inválido, portal/usuário sem grupo, outra empresa/owner e alvo não autorizado negados, sem efeitos no banco |
| Payload | JSON quebrado, array, NaN, tipos inválidos, vazios, mídia/URL maliciosa e excesso com/sem Content-Length rejeitados |
| Fontes | Markdown/TXT e PDF/DOCX reais chegam a waiting_review; YouTube fixture preserva timings/idioma e ausência de transcript nunca vira sucesso |
| Revisão | Conteúdo inexistente antes do aceite; revisor aprova, recusa e edita; conteúdo real depois de aprovar; operator não publica |
| Idempotência | Replays e pelo menos duas submissões/aprovações concorrentes não duplicam; payload diferente 409; timestamp de catálogo não muda identidade |
| Recovery | Falha/timeout controlado no provider, restart após checkpoint, retry limitado, cancelamento e saída de stale running verificados |
| Privacidade | Artefatos/Project privados, isolamento usuário/empresa, HTML escapado e logs redigidos |
| Legado | Testes do fluxo anterior e asserções de nenhum novo hook/chamada a facodi-ai/facodi-learning; processamento novo disabled continua inerte |
| Reprodutibilidade | Checkout limpo, comando único, saída não-zero em falha e relatório por cenário vinculado ao SHA final |

Adicione smoke opt-in de provider externo real e aquisição YouTube permitida, somente com credenciais de teste independentes e budget. Se não houver credenciais/rede, registre NOT_EXECUTED e limite a conclusão a E2E determinístico; não afirme provider real validado. Se essa integração real for requisito da release, a release permanece bloqueada.

## 8. Evidências, CI e documentação

Guarde relatórios sanitizados em docs/facodi-api/e2e/ com matriz PASS/FAIL/BLOCKED/NOT_EXECUTED, data, comandos, exit codes, versões, SHAs, tempos, IDs de runs/tarefas/conteúdo e asserções. Logs volumosos ficam como artifacts da CI, sem segredos. Capturas de tela podem complementar; nunca substituir asserções.

Configure CI standalone e integração/E2E isolado, sem jobs de produção. Execute toda a suíte no commit final, compile/lint relevantes, instalação limpa e upgrade. Não aceite skip/xfail/bloqueio em cenário obrigatório. Prove ainda que uma falha forçada faz o comando E2E retornar não-zero; depois remova a falha e execute a suíte final novamente.

Atualize README, OpenAPI, runbook, arquitetura, instruções de teste, migrations/rollback, limites do provider e diferenças baseline/IA. Cada issue concluída deve ter PR e evidência específica; não encerrar em massa com pytest unitário. #11/#12 e cutover permanecem futuros. Prepare PRs revisáveis nos dois repositórios, com alterações de deploy somente em branch de teste; não faça merge ou deploy.

## 9. Regra de parada e entrega final

Continue corrigindo até que o contrato e a matriz obrigatória funcionem E2E no ambiente isolado. Planejar passos futuros, retornar 501, simular publicação, usar ORM manual em vez de HTTP/fila, executar em produção ou reportar somente testes unitários NÃO é conclusão.

Ao terminar, entregue: links de PR/commits, comando exato de reprodução, matriz por cenário, relatório, número real de testes, prova do conteúdo publicado no ambiente de teste, recovery/replay e limitações de rede/provider. Declare separadamente: engine offline, integração Odoo, E2E determinístico e integrações externas reais. Só diga API concluída quando todo o escopo contratado tiver evidência; implantação e cutover continuam fora desta autorização.

## 10. Validação adicional via MCP Odoo

A auditoria consultou produção somente em leitura: addon instalado, cron id 26 ativo, runs 1/3 published, run 3 com 0 candidatos, tarefas 4–6 sem subtarefas, projeto 2 com visibility portal e busca exata de títulos sem slide.slide. Não interprete esses registros como publicação E2E comprovada. Não alterar/remover esses objetos para fazer o teste passar.

Inclua MCP no ambiente descartável: primeiro descubra conexões/URL/banco, selecione explicitamente a conexão de TESTE em cada chamada e rejeite produção/default automático. Teste conectividade, modelos/campos, consulta da execução criada pelo HTTP, artefatos, tarefas/subtarefas e conteúdo publicado. Exercite operações/métodos de revisão autorizados via MCP somente nos registros sintéticos desse ambiente; valide permissões e retornos serializáveis. MCP não deve contornar invariantes de autorização, revisão ou idempotência aplicadas no HTTP.

Use uma chave dedicada de teste com permissões mínimas; não habilite modelos/ações globais em produção. Respeite limite de chamadas e faça consultas agrupadas. Se não houver conexão MCP para o ambiente descartável, registre MCP_MUTATION_E2E=BLOCKED e prepare configuração/documentação para conectar; não usar a conexão de produção como fallback. Consultas read-only em produção autorizadas para auditoria são evidência separada, não substituem esse cenário. Endpoints HTTP reais e worker continuam obrigatórios mesmo quando MCP funciona.
