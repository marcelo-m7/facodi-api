# Espelho operacional em Odoo Project standard

## Configuração

Projeto `FACODI — Content Pipeline`, XML ID `facodi_api.project_content_pipeline`, privado para equipa interna (`privacy_visibility=followers`). Ativar dependências standard `allow_task_dependencies`. Milestones propostos para engenharia não são milestones de conteúdo: este projeto acompanha execuções reais, não issues GitHub. Não depender de Project Templates Enterprise; criar as tarefas por ORM e XML IDs idempotentes.

Uma tarefa principal por run, com nome legível e referência curta do UUID. Subtarefas usam `parent_id`, `project_id`, `depend_on_ids`, `user_ids`, `stage_id` standard. Novos campos apenas de ligação: `facodi_pipeline_run_id`, `facodi_pipeline_step_id`; readonly, `copy=False`, record rules. Não colocar transcript, chave de API, payload bruto nem informações pessoais no título/chatter.

| Etapa técnica | Subtarefa | Predecessoras | Responsável |
| --- | --- | --- | --- |
| `ingest` | 01 · Ingest source | nenhuma | executor técnico |
| `normalize` | 02 · Normalize document | ingest | executor |
| `enrich` | 03 · Enrich with evidence | normalize | executor |
| `map_courses` | 04 · Map existing courses and content | enrich | executor |
| `map_curriculum` | 05 · Map existing curriculum | enrich | executor |
| `persist` | 06 · Persist editorial proposals | dois mappings habilitados | executor |
| `review` | 07 · Review evidence and proposals | persist | eLearning Manager |
| `publish` | 08 · Publish canonical content | review + comando explícito | Manager |

Capabilities isoladas criam apenas subtarefas habilitadas. Subpassos internos, como listar legendas ou dividir chunks, geram evento sanitizado/artefacto e duração na subtarefa correspondente; não uma tarefa por chunk/frame/request. Retry preserva a mesma subtarefa e regista nova tentativa técnica. Novo processamento deliberado com versão diferente gera novo run/tarefa, ligado à submissão anterior.

## Estado humano versus estado técnico

Stages próprios do projeto, source labels em inglês para tradução nativa: Queued, Processing, Waiting for input, Review, Ready to publish, Published, Failed, Cancelled. Usar Odoo `state` standard para fechar tarefas; nunca estender o enum global com estados da pipeline. Mover `stage_id` não é o mesmo que completar a tarefa; mapeamento é explícito.

| Situação | Project |
| --- | --- |
| queued / pending | Queued, tarefa aberta |
| running | Processing, aberta |
| waiting_input / retry_wait | Waiting for input; atividade para editor no primeiro caso |
| review_required | Review; uma atividade deduplicada para Manager |
| ready | Ready to publish; aberta |
| step succeeded | etapa concluída usando estado standard |
| capability succeeded | principal concluída; artefacto continua privado |
| run published | Published; principal concluída |
| failed | Failed, aberta para triagem; resumo sem resposta bruta |
| cancelled | Cancelled, estado de cancelamento standard |

Odoo pode tratar tarefas canceladas como fechadas para dependências. Por isso, o scheduler valida estados técnicos independentemente da UI: uma etapa cancelada nunca é equivalente a sucesso. Não usar o Kanban como fila de execução.

## Interação

Smart buttons `Pipeline`, `Submission`, `Analysis`, `Source`, `Canonical Content` só aparecem quando o ator consegue ler o alvo. Ações `Retry`, `Cancel`, `Open review`, `Publish` chamam os mesmos serviços usados pela API. `Publish` exige Manager e decisão atual; arrastar para Published ou marcar Done é bloqueado/reconciliado nos campos geridos sem afetar tarefas comuns.

Chatter regista queued, início/fim de cada etapa, retry, intervenção e links autorizados. Um evento por transição significativa, não por token. `mail.activity` marca pendência/revisão/erro terminal com deduplicação e encerra apenas a atividade criada pela pipeline. Não adicionar o contribuidor como follower de tarefa técnica nem convidar Portal ao projeto. As mensagens automáticas e atividades pertencem ao fluxo solicitado; não enviar emails avulsos a terceiros.

## Permissões e consistência

Executor técnico não usa conta admin e não recebe publicação; acesso de background conserva o ator original para autorização dos inputs. Manager e equipa Project autorizada veem tasks privadas. Contribuidor consulta somente a projeção segura do estado pelo mecanismo existente de submissões; não vê payload, logs, outras submissões, task IDs nem attachments técnicos.

Criar run, parent task e subtarefas na mesma transação. Constraint única por run/step. `project.task.copy()` não duplica ligações técnicas; tasks geridas não podem ser apagadas enquanto vinculadas a runs retidos. Renomear uma task standard é permitido; não usar o nome como identidade. Arquivar projeto/etapa não apaga o run; interromper execução com erro de configuração seguro se o espelho obrigatório ficar indisponível. Testar rollback transacional e reconciliação de stages sem tocar em tarefas de outros projetos.

## Storytelling de aceitação

1. Um estudante sugere vídeo numa UC; o contexto permanece na submissão existente.
2. A equipa vê a tarefa principal e etapas, sem expor o contacto do estudante.
3. Sem legenda, subtarefa pede transcrição; as etapas seguintes ficam bloqueadas.
4. Com legenda, sugestões mostram excertos e minutos; mapping aponta a cursos/UCs reais.
5. Manager aprova/rejeita pelas ações de domínio e abre a publicação explícita.
6. A tarefa só termina Published após confirmar persistência standard; replay não duplica.
