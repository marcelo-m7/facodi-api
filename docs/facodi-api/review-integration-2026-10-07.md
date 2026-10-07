# Revisão e integração da entrega de 7 de outubro de 2026

Entrega de origem: API PR #16 (`9b8c942`) e deploy PR #261 (`4de0b75`). O relatório do agente comprova intenção de teste; a aceitação desta revisão depende das execuções do CI e do MCP registradas ao final deste documento.

## Correções da revisão

- Create/write ORM protegem identidade, entrada aceita, estado, resultados e aprovação; contexto fornecido pelo cliente não autoriza mudanças.
- Curso, catálogo e publicação ficam vinculados ao website e empresa aceitos. Regras nativas de manager de eLearning não bastam para esse isolamento.
- HTTP respeita Content-Length e limita corpo chunked. Conteúdo vazio é recusado antes de gerar tarefas.
- Execução exige received e lock exclusivo; cron verifica administrador antes de consultar/lockar a fila, processa um registro por chamada e usa proprietário e empresa registrados.
- Falhas de aquisição retornam códigos sanitizados; logs do modelo não incluem exceções completas do provedor.
- YouTube tem processo filho com encerramento em 45 segundos, sessão com timeout, orçamento de aquisição, limite de resposta, segmentos e transcrição. Texto manual exige marcação explícita e nunca comprova aquisição automática.
- Publicação de YouTube preserva o vídeo canônico em slide.slide; artigos continuam usando HTML escapado.
- Addon versionado em 19.0.2.0.0. Migração preserva o estado antigo em legacy_status e coloca registros anteriores em quarentena, sem inferir publicação, revisão ou propriedade verificada. Payloads, artefatos e relações históricas são preservados. O pipeline permanece desligado durante a migração.
- Deploy instala/atualiza facodi_api, instala requirements no interpretador Odoo e guarda artefatos no volume existente odoo-data. Nenhum consumidor legado foi desviado nesta entrega.

## Validação e limitações

Testes puros locais: 56 passed, 1 skipped (suite ORM exige Odoo real). Deploy: 50 contratos passam; execução Docker ocorrerá no CI porque este ambiente não tem daemon Docker.

O CI de API runtime verifica instalação com testes ORM, upgrades, gate HTTP fechado, HTTP 202, limites, keep-alive, idempotência concorrente, isolamento de papéis, lock com dois cursores, scheduler real, publicação e persistência após restart. O CI principal verifica a imagem de produção e os fluxos atuais da plataforma.

O provedor padrão ainda é baseline determinístico. Não corresponde a enriquecimento LLM externo nem a alinhamento curricular oficial completo. Capabilities/OpenAPI, filas de retomada, integração UI e retirada de consumidores legados continuam como trabalho posterior.

## Resultado operacional

Pendente nesta revisão: URLs de execuções, SHAs finais de main, confirmação do build/migração, verificações via MCP e resultado real de aquisição de cada vídeo. Atualizar esta seção com evidência antes de declarar integração operacional.
