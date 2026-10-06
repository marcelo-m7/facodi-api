# Bibliotecas, evidência e política de dependências

Pesquisa e inspeção de fontes em 2026-10-06. Suporte anunciado numa biblioteca não prova instalação compatível nem disponibilidade do vídeo. Versões exatas serão produzidas pelo ensaio A05/D01 na imagem Odoo real; não inventar pins neste documento.

| Ferramenta | Uso proposto | Decisão |
| --- | --- | --- |
| Microsoft MarkItDown | converter documentos/HTML e URLs YouTube em Markdown | adapter interno; extras mínimos, plugins desativados |
| `youtube-transcript-api` | recuperar segmentos, timestamps, idioma e tipo de legenda | adapter explícito YouTube; evita perder a evidência temporal |
| Python `dataclasses`, `typing`, `hashlib`, `urllib.parse`, `ipaddress` | DTOs, protocolos, hashes, URL validation | standard library |
| `requests` | sessões HTTP com timeouts e fetch controlado | já usado no repo; configuração interna, nunca do cliente |
| `facodi_ai` / `pydantic_ai` já existentes | chamadas LLM estruturadas e auditadas | reutilizar serviço e segredo configurados, sem engine IA paralelo |
| `jsonschema` em ambiente de desenvolvimento | validar futuros JSON Schemas/OpenAPI | opcional de testes, sem impor Pydantic novo ao runtime Odoo |
| scikit-learn / sentence-transformers | retrieval/embeddings futuros | fora de M1; só após benchmark mostrar necessidade |
| FFmpeg / Whisper / faster-whisper | ASR de conteúdo sem legenda | fora do primeiro release; não instalar GPU/áudio implicitamente |
| OCA `queue_job` / Celery / FastAPI | execução externa/subsegundo | não obrigatórios; cron standard primeiro |

## MarkItDown

O nome correto é **MarkItDown**, projeto Python da Microsoft. README confirma URLs YouTube e extras por formato; `youtube-transcription` fornece a dependência de transcrições. PDF, DOCX e PPTX podem entrar pelo mesmo adapter numa fase seguinte.

O código atual de `YouTubeConverter` recupera metadata/legenda e concatena `part.text`; o Markdown não guarda os timestamps. Pode devolver título/descrição sem transcrição. Portanto a presença de Markdown não basta: o adapter FACODI inspeciona separadamente a disponibilidade e preserva segmentos. Quando o provider direto já extraiu legenda, compor Markdown a partir dessa evidência evita buscar a mesma legenda duas vezes.

Para documentos, usar `convert_stream()` com stream adquirido e validado; nunca passar ao conversor um caminho local ou URL arbitrária enviado pelo cliente. O README do projeto informa que a ferramenta faz I/O com os privilégios do processo. Desativar plugins e conversões LLM implícitas. Um subprocesso de conversão limitado, sem ORM/credenciais, pode ser chamado pela lógica dentro do addon; não é um microserviço externo.

## Transcrição YouTube

A biblioteca `youtube-transcript-api` permite selecionar idiomas, legendas humanas/automáticas e recuperar texto, start/duration. É uma integração com interface não documentada do YouTube, não a API oficial de transcrições garantida pelo fornecedor. O README relata bloqueios de IPs de cloud/self-hosting e indisponibilidade de alguns vídeos.

Política: normalizar ID e URL HTTPS dos hosts permitidos; preferir idioma pedido e legenda humana; registrar escolha, geração automática e tradução. `RequestBlocked`, vídeo privado/removido, legenda ausente e idioma inexistente são casos distintos. Não iniciar ASR, tradução, proxy pago ou download de áudio automaticamente. Permitir transcrição enviada pelo editor como attachment privado com provenance `manual_transcript`.

## Compatibilidade e instalação

1. Inspecionar `python3 --version` em `odoo:19.0` e os pacotes existentes de `/opt/facodi-venv`.
2. Resolver `markitdown[youtube-transcription]`, extras documentais de M2 e `youtube-transcript-api` numa venv descartável compatível; testar conflitos com OpenSSL, cryptography e pydantic_ai já requeridos.
3. Gerar requirements lock com versões transitivas e hashes após o ensaio; manter input legível em `requirements.in` no owner API. Não instalar `[all]` indiscriminadamente.
4. Docker instala o lock durante build; `external_dependencies` no manifest declara módulos Python requeridos mas não instala pacotes.
5. Confirmar imports, `pip check` e conversão com fixtures sem rede no mesmo interpreter que executa Odoo.
6. Rede real YouTube é ensaio opt-in em staging; CI normal usa transcripts/HTML autorizados de teste, sem secretos/live URLs.

## Fontes primárias

- [Microsoft MarkItDown — README](https://github.com/microsoft/markitdown): formatos, extras, Python e segurança de I/O.
- [MarkItDown — dependências](https://github.com/microsoft/markitdown/blob/main/packages/markitdown/pyproject.toml).
- [YouTube converter — implementação](https://github.com/microsoft/markitdown/blob/main/packages/markitdown/src/markitdown/converters/_youtube_converter.py): concatenação da legenda e comportamento de fallback.
- [youtube-transcript-api — README](https://github.com/jdepoix/youtube-transcript-api): segmentos, idiomas, bloqueios e API não documentada.
- [Odoo 19 — controllers](https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html): `http`, `jsonrpc`, autenticação bearer.
- [Odoo 19 — cron e batching](https://www.odoo.com/documentation/19.0/developer/reference/backend/actions.html#scheduled-actions-ir-cron).
- [Fonte do cron 19.0](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_cron.py) e [documentação fonte](https://github.com/odoo/documentation/blob/19.0/content/developer/reference/backend/actions.rst).
- [Odoo Project 19.0 — tarefas](https://github.com/odoo/odoo/blob/19.0/addons/project/models/project_task.py) e [projeto](https://github.com/odoo/odoo/blob/19.0/addons/project/models/project_project.py): subtarefas, dependências e milestones na Community.

URLs `main` upstream podem mudar. O lock e o relatório de compatibilidade devem registrar release/SHA realmente testado. Estas fontes fundamentam possibilidades e limites; nenhuma benchmark da FACODI foi executada nesta entrega documental.
