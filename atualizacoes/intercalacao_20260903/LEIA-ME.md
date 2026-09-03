# Power Streaming — atendimento e base fria intercalados

Versão da atualização: **2026.09.03-intercalacao.1**.

Este é um **atualizador incremental do programa Python já instalado**, não um bot completo. Não execute o `index.js` nem instale dependências do projeto Node.js para usar esta atualização.

## Instalar no Windows

1. Pare o bot com **Ctrl+C**. Feche outras instâncias do Power Streaming.
2. Extraia o ZIP inteiro. Se o download veio do GitHub, entre em `atualizacoes/intercalacao_20260903`.
3. Na pasta da atualização, dê dois cliques em **ATUALIZAR.bat**.
4. Confira que o alvo é `C:\power_streaming\atendimento_whatsapp.py`. Digite **ATUALIZAR** somente com o bot parado.
5. O atualizador cria uma cópia do script original, valida a versão e aplica a mudança de forma atômica.
6. Inicie pelo procedimento que já funciona no seu computador e escolha **1** (ou **5**, para manter o painel).

No terminal aparecerá: `[BASE FRIA] Intercalacao ativa nos modos 1 e 5`.

Se usa outra pasta, execute `aplicar_atualizacao.py --arquivo "CAMINHO\atendimento_whatsapp.py"` com o Python do ambiente do bot. A opção `--verificar` apenas confere a compatibilidade, sem gravar.

**Não copie `funcoes_intercaladas.py` sobre o programa e não execute esse arquivo sozinho.** Ele contém somente os trechos utilizados pelo atualizador.

## O que muda

- O modo 1 continua atendendo e também aborda um contato elegível com status `Lead Frio` por vez. O modo 5 usa o mesmo agendador.
- A mensagem de apresentação do IAgo permanece exatamente a da versão enviada.
- Antes e depois de cada rotina automática, há nova passagem pelo atendimento. Também há checagem entre painel e alertas.
- No máximo **uma** rotina agendada (base fria, verificação diária ou follow-up) roda por ciclo. A mais atrasada ganha a vez; não há lote acumulado de contatos atrasados.
- Mensagens prontas para atendimento e novos chats não lidos têm prioridade. Pendências aguardando nova tentativa não bloqueiam todos os demais contatos; o próprio contato com pendência continua fora da base fria.
- O intervalo da base fria continua entre **5 e 7 minutos**, contado a partir do fim da tentativa. Adiar por atendimento não reinicia esse prazo.
- O terminal informa quando a base fria está no prazo, mas aguarda atendimento ou a sua vez entre as rotinas.

## O que permanece intacto

O atualizador altera somente `executar_ciclo` e acrescenta duas funções auxiliares no próprio `atendimento_whatsapp.py`. A estrutura das outras **76 funções** do arquivo enviado, das classes, configurações, imports e menu é comparada antes de qualquer gravação.

Não substitui nem altera:

- `clientes.xlsx` e suas colunas ou registros;
- `estado_bot.sqlite3`, histórico, pendências e confirmações;
- `conhecimento_empresa.txt`;
- `confiabilidade.py` e `navegacao.py`;
- API, número de controle, regras de bloqueio e modo manual;
- `INICIAR.bat`, ambiente virtual e login do WhatsApp.

O envio continua usando as verificações já existentes. Um lead só é registrado como abordado após confirmação; duplicados, bloqueados e contatos com pendência mantêm as regras anteriores. O atualizador não importa o bot, não abre o navegador e não envia mensagens.

## Proteção contra perda de versão

O pacote aceita apenas a revisão Python enviada em 03/09/2026, identificada por SHA-256 do texto normalizado:

`3a822a5b2440794be12fbdc259f8442186a90883ef7c012f826dd0101de90532`

Aceita quebras Windows/Linux e BOM UTF-8. Se houver qualquer outra alteração no arquivo, **recusa a instalação**, em vez de substituí-la por uma versão antiga. Nesse caso, envie o script atual para adaptação. Reaplicar a mesma atualização não duplica as funções.

A cópia fica ao lado do script com o nome `atendimento_whatsapp.py.antes_intercalacao_DATA_IDENTIFICADOR.bak`. Para voltar, pare o bot, preserve o script atualizado com outro nome e copie o backup para `atendimento_whatsapp.py`. **Não restaure a planilha ou o banco:** a atualização não os modifica, e o histórico de envios deve ser preservado.

## Testes e limites

Os testes automatizados usam relógio, navegador, filas e dados simulados, sem clientes reais. Também há verificações sobre o arquivo enviado, sem executar seu código de inicialização. Execute `python -m unittest discover -s tests -v` dentro desta pasta.

A validação no Windows com WhatsApp Web e a versão instalada de `navegacao.py`/`confiabilidade.py` ainda precisa ocorrer; esses módulos atuais não foram anexados. Eles são mantidos como estão, sem substituição por cópias antigas.

O Selenium permanece em uma única thread. Uma abertura/envio já em andamento termina ou atinge seu timeout antes da próxima checagem: não há promessa de interrupção instantânea de um envio nem de ausência absoluta de regressões. Mantenha a primeira execução supervisionada e verifique atendimento, apresentação, confirmação e ausência de duplicidade.

O pacote contém somente este atualizador, seus trechos e testes. Configurações privadas, base de clientes, sessão e script completo não estão incluídos. A publicação no repositório público depende de autorização explícita do proprietário.
