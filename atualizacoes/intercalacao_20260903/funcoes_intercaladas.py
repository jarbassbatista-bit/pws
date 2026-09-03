"""Trechos aplicados ao bot existente; este arquivo nao inicia o WhatsApp.

As dependencias globais sao as do atendimento_whatsapp.py original.
Nao importar este arquivo como um programa independente.
"""


def ha_atendimento_pronto(driver):
    """Prioriza trabalho pronto, sem travar tudo por uma pendencia em backoff."""
    agora = time.time()
    estado = estado_bot()
    wb = None
    for _, job in estado.listar('entrada:'):
        if job.get('status') != 'pendente' or job.get('retry', 0) > agora:
            continue
        telefone, nome = job.get('telefone', ''), job.get('nome', '')
        if normalizar_telefone_br(telefone) == NUMERO_CONTROLE_DONO:
            return True
        if wb is None:
            wb = abrir_planilha()
        linha = buscar_contato(wb.active, telefone, nome)
        if not impedido(telefone, nome, linha, ativo=True):
            return True
    for _, item in estado.listar('chat_retry:'):
        if not item.get('resolvido') and item.get('retry', 0) <= agora:
            return True
    # Nova leitura imediatamente antes de uma rotina: pode haver mensagem que
    # chegou enquanto o painel/alerta estava sendo processado. Falha na leitura
    # e propagada para adiar a rotina, nunca interpretada como caixa vazia.
    for chat in listar_chats_nao_lidos(driver):
        item = estado.get('chat_retry:' + chat['nome'], {})
        if item and not item.get('resolvido') and item.get('retry', 0) > agora:
            continue
        return True
    return False


def informar_status_intercalacao(agenda):
    agora = time.time()
    if agora < agenda.get('status', 0):
        return
    agenda['status'] = agora + 30
    jobs = [j for _, j in estado_bot().listar('entrada:') if j.get('status') == 'pendente']
    espera = max(0, int(agenda.get('frio', agora) - agora))
    if espera:
        situacao = f'proxima base fria em {espera}s'
    else:
        situacao = 'base fria no prazo; ' + agenda.get('motivo_espera', 'aguardando sua vez')
    print(f'[ATIVO] Monitoramento em execucao | {len(jobs)} pendencia(s) | '
          f'{fila_acoes_web.qsize()} acao(oes) no painel | {situacao}')


def executar_ciclo(driver, agenda):
    """Intercala atendimento com no maximo UMA rotina automatica por ciclo.

    O Selenium continua em uma unica thread. Agenda usa o fim da tentativa,
    nao acumula disparos atrasados e nao consome o prazo quando adia por fila.
    Pendencias em espera nao bloqueiam outros contatos (regra preexistente).
    """
    if not agenda.get('intercalacao_anunciada'):
        print('[BASE FRIA] Intercalacao ativa nos modos 1 e 5: um lead por vez, '
              f'intervalo de {MINUTOS_MIN_ENTRE_ABORDAGENS_FRIAS} a '
              f'{MINUTOS_MAX_ENTRE_ABORDAGENS_FRIAS} minutos; atendimento prioritario.')
        agenda['intercalacao_anunciada'] = True

    def executar_etapa(nome, acao):
        try:
            acao()
            return True
        except Exception as exc:
            print(f'[CICLO/{nome}] {type(exc).__name__}: {exc}')
            return False

    try:
        leitura_ok = executar_etapa('atendimento', lambda: atender_entre_envios(driver))
        # Comandos do painel e alertas ao dono continuam independentes; o
        # atendimento volta a ser consultado entre essas etapas.
        executar_etapa('painel', lambda: processar_fila_acoes_web(driver))
        leitura_ok = executar_etapa('atendimento', lambda: atender_entre_envios(driver)) and leitura_ok
        executar_etapa('alertas', lambda: enviar_alertas_pendentes(driver))

        agora = time.time()
        rotinas = [
            ('frio', 'base fria', lambda: processar_proximo_lead_frio(driver)),
            ('diario', 'rotinas', lambda: rodar_verificacoes_diarias(driver, limite_envios=1)),
            ('followup', 'followup', lambda: verificar_followups_teste_60min(driver, limite_envios=1)),
        ]
        vencidas = [r for r in rotinas if agora >= agenda.get(r[0], 0)]
        if not vencidas:
            return

        leitura_ok = executar_etapa('atendimento', lambda: atender_entre_envios(driver)) and leitura_ok
        if not leitura_ok:
            agenda['motivo_espera'] = 'checagem do atendimento sera repetida'
            return
        try:
            prioridade = ha_atendimento_pronto(driver)
        except Exception as exc:
            print(f'[CICLO/prioridade] {type(exc).__name__}: {exc}')
            agenda['motivo_espera'] = 'checagem do atendimento indisponivel'
            return
        if prioridade:
            agenda['motivo_espera'] = 'aguardando atendimento prioritario'
            return

        # A mais atrasada ganha a vez. Empate favorece a base fria. As outras
        # seguem vencidas para o proximo ciclo, sem serem marcadas como feitas.
        chave, nome, acao = min(vencidas, key=lambda r: agenda.get(r[0], 0))
        agenda['motivo_espera'] = 'aguardando sua vez entre as rotinas'
        if chave == 'frio':
            print('[BASE FRIA] Verificando ate um lead elegivel; depois retorno ao atendimento.')
        try:
            executar_etapa(nome, acao)
        finally:
            intervalo = (random.uniform(MINUTOS_MIN_ENTRE_ABORDAGENS_FRIAS * 60,
                                        MINUTOS_MAX_ENTRE_ABORDAGENS_FRIAS * 60)
                         if chave == 'frio' else 60 if chave == 'diario' else 300)
            agenda[chave] = time.time() + intervalo
            executar_etapa('atendimento', lambda: atender_entre_envios(driver))
    finally:
        informar_status_intercalacao(agenda)
