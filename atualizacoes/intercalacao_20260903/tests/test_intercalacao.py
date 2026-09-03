import ast
import copy
import importlib.util
import io
import os
from pathlib import Path
import queue
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch


RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atualizador', RAIZ / 'aplicar_atualizacao.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
TRECHOS = (RAIZ / 'funcoes_intercaladas.py').read_text(encoding='utf-8')


class EstadoFake:
    def __init__(self):
        self.dados = {}

    def get(self, chave, padrao=None):
        return copy.deepcopy(self.dados.get(chave, padrao))

    def set(self, chave, valor):
        self.dados[chave] = copy.deepcopy(valor)

    def listar(self, prefixo):
        return [(k, copy.deepcopy(v)) for k, v in self.dados.items() if k.startswith(prefixo)]


class TestCiclo(unittest.TestCase):
    def setUp(self):
        self.agora = 1000
        self.estado = EstadoFake()
        self.eventos = []
        self.saida = io.StringIO()
        self.ctx = redirect_stdout(self.saida)
        self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)
        self.ns = {
            'time': SimpleNamespace(time=lambda: self.agora),
            'random': SimpleNamespace(uniform=Mock(return_value=360)),
            'estado_bot': lambda: self.estado,
            'normalizar_telefone_br': lambda t: t,
            'NUMERO_CONTROLE_DONO': 'dono-teste',
            'abrir_planilha': Mock(return_value=SimpleNamespace(active='aba-teste')),
            'buscar_contato': Mock(return_value=None),
            'impedido': Mock(return_value=False),
            'listar_chats_nao_lidos': Mock(return_value=[]),
            'fila_acoes_web': queue.Queue(),
            'MINUTOS_MIN_ENTRE_ABORDAGENS_FRIAS': 5,
            'MINUTOS_MAX_ENTRE_ABORDAGENS_FRIAS': 7,
        }
        for func, rotulo in [
            ('atender_entre_envios', 'atendimento'),
            ('processar_fila_acoes_web', 'painel'),
            ('enviar_alertas_pendentes', 'alertas'),
            ('processar_proximo_lead_frio', 'frio'),
            ('rodar_verificacoes_diarias', 'diario'),
            ('verificar_followups_teste_60min', 'followup'),
        ]:
            self.ns[func] = Mock(side_effect=lambda *a, r=rotulo, **kw: self.eventos.append(r))
        exec(compile(TRECHOS, 'funcoes_intercaladas.py', 'exec'), self.ns)
        self.driver = object()
        self.agenda = {'frio': 900, 'diario': 2000, 'followup': 2000, 'status': 2000}

    def ciclo(self):
        self.ns['executar_ciclo'](self.driver, self.agenda)

    def pendencia(self, retry=0, telefone='contato-teste', status='pendente'):
        self.estado.set('entrada:teste', {'telefone': telefone, 'nome': 'Teste',
                                       'status': status, 'retry': retry})

    def test_atende_antes_e_depois_de_um_unico_lead(self):
        self.ciclo()
        self.assertEqual(self.eventos, ['atendimento', 'painel', 'atendimento',
                                       'alertas', 'atendimento', 'frio', 'atendimento'])
        self.ns['processar_proximo_lead_frio'].assert_called_once_with(self.driver)

    def test_fila_pronta_adia_sem_consumir_prazo(self):
        self.pendencia()
        self.ciclo()
        self.assertNotIn('frio', self.eventos)
        self.assertEqual(self.agenda['frio'], 900)
        self.assertIn('prioritario', self.agenda['motivo_espera'])

    def test_retomada_apos_atendimento_sem_nova_espera_de_sete_minutos(self):
        self.pendencia()
        self.ciclo()
        self.pendencia(status='concluida')
        self.ciclo()
        self.assertEqual(self.eventos.count('frio'), 1)

    def test_pendencia_em_backoff_nao_trava_todos(self):
        self.pendencia(retry=1100)
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_pendencia_manual_nao_trava_todos(self):
        self.pendencia()
        self.ns['impedido'].return_value = True
        self.ciclo()
        self.assertIn('frio', self.eventos)
        self.ns['impedido'].assert_called_with('contato-teste', 'Teste', None, ativo=True)

    def test_comando_dono_tem_prioridade(self):
        self.pendencia(telefone='dono-teste')
        self.ciclo()
        self.assertNotIn('frio', self.eventos)

    def test_chat_retry_pronto_tem_prioridade(self):
        self.estado.set('chat_retry:Teste', {'nome': 'Teste', 'retry': 0})
        self.ciclo()
        self.assertNotIn('frio', self.eventos)

    def test_chat_retry_em_backoff_nao_trava_todos(self):
        self.estado.set('chat_retry:Teste', {'nome': 'Teste', 'retry': 1100})
        self.ns['listar_chats_nao_lidos'].return_value = [{'nome': 'Teste'}]
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_chat_resolvido_sem_nova_mensagem_nao_bloqueia(self):
        self.estado.set('chat_retry:Teste', {'nome': 'Teste', 'retry': 0, 'resolvido': True})
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_nova_mensagem_apos_chat_resolvido_tem_prioridade(self):
        self.estado.set('chat_retry:Teste', {'nome': 'Teste', 'retry': 1100, 'resolvido': True})
        self.ns['listar_chats_nao_lidos'].return_value = [{'nome': 'Teste'}]
        self.ciclo()
        self.assertNotIn('frio', self.eventos)

    def test_novo_nao_lido_apos_alerta_adia_prospeccao(self):
        def alerta(*args):
            self.ns['listar_chats_nao_lidos'].return_value = [{'nome': 'Novo'}]
        self.ns['enviar_alertas_pendentes'].side_effect = alerta
        self.ciclo()
        self.assertNotIn('frio', self.eventos)
        self.assertEqual(self.agenda['frio'], 900)

    def test_falha_na_leitura_nao_significa_fila_vazia(self):
        self.ns['listar_chats_nao_lidos'].side_effect = RuntimeError('offline')
        self.ciclo()
        self.assertNotIn('frio', self.eventos)
        self.assertIn('indisponivel', self.agenda['motivo_espera'])

    def test_falha_do_atendimento_adia_rotina(self):
        self.ns['atender_entre_envios'].side_effect = RuntimeError('falha')
        self.ciclo()
        self.assertNotIn('frio', self.eventos)
        self.assertEqual(self.agenda['frio'], 900)

    def test_falha_painel_nao_desativa_base_fria(self):
        self.ns['processar_fila_acoes_web'].side_effect = RuntimeError('falha')
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_falha_alerta_nao_desativa_base_fria(self):
        self.ns['enviar_alertas_pendentes'].side_effect = RuntimeError('falha')
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_falha_na_base_fria_reagenda_e_volta_ao_atendimento(self):
        self.ns['processar_proximo_lead_frio'].side_effect = RuntimeError('falha')
        self.ciclo()
        self.assertEqual(self.agenda['frio'], 1360)
        self.assertEqual(self.eventos[-1], 'atendimento')

    def test_tentativa_longa_conta_intervalo_a_partir_do_final(self):
        def fria(*args):
            self.agora += 90
        self.ns['processar_proximo_lead_frio'].side_effect = fria
        self.ciclo()
        self.assertEqual(self.agenda['frio'], 1450)
        self.ns['random'].uniform.assert_called_once_with(300, 420)

    def test_nao_envia_antes_do_prazo(self):
        self.agenda['frio'] = 1001
        self.ciclo()
        self.assertNotIn('frio', self.eventos)

    def test_ciclos_rapidos_nao_formam_lote(self):
        for _ in range(10):
            self.ciclo()
            self.agora += 2
        self.assertEqual(self.eventos.count('frio'), 1)

    def test_todas_vencidas_executam_uma_por_ciclo(self):
        self.agenda.update(frio=900, diario=900, followup=900)
        self.ciclo()
        self.assertEqual([x for x in self.eventos if x in ('frio', 'diario', 'followup')], ['frio'])
        self.assertEqual(self.agenda['diario'], 900)
        self.assertEqual(self.agenda['followup'], 900)
        self.ciclo()
        self.ciclo()
        self.assertEqual([x for x in self.eventos if x in ('frio', 'diario', 'followup')],
                         ['frio', 'diario', 'followup'])
        self.ns['rodar_verificacoes_diarias'].assert_called_once_with(self.driver, limite_envios=1)
        self.ns['verificar_followups_teste_60min'].assert_called_once_with(self.driver, limite_envios=1)

    def test_rotina_mais_antiga_ganha_vez_sem_descartar_base(self):
        self.agenda['diario'] = 800
        self.ciclo()
        self.assertIn('diario', self.eventos)
        self.assertNotIn('frio', self.eventos)
        self.assertEqual(self.agenda['frio'], 900)
        self.ciclo()
        self.assertIn('frio', self.eventos)

    def test_status_informa_motivo_da_espera(self):
        self.agenda['status'] = 0
        self.pendencia()
        self.ciclo()
        self.assertIn('base fria no prazo; aguardando atendimento prioritario', self.saida.getvalue())

    def test_status_e_banner_nao_polui_cada_ciclo(self):
        self.agenda['status'] = 0
        self.ciclo()
        self.ciclo()
        self.assertEqual(self.saida.getvalue().count('[ATIVO]'), 1)
        self.assertEqual(self.saida.getvalue().count('Intercalacao ativa'), 1)

    def test_agenda_sem_campos_nao_quebra_status(self):
        self.agenda.clear()
        self.ciclo()
        self.assertIn('[ATIVO]', self.saida.getvalue())


BASE_SINTETICA = '''import os
CONFIGURACAO = "nao alterar"
def apresentacao():
    return "IAgo"
def executar_ciclo(driver, agenda):
    return "versao anterior"
def outras_funcoes():
    return 42
if __name__ == "__main__":
    raise RuntimeError("Nao executar o bot no atualizador")
'''


class TestAtualizador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.arquivo = self.raiz / 'atendimento_whatsapp.py'
        self.arquivo.write_text(BASE_SINTETICA, encoding='utf-8')
        self.patcher = patch.object(u, 'SHA_BASE', u.assinatura(BASE_SINTETICA))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_backup_exato_e_outros_arquivos_intactos(self):
        nomes = ['clientes.xlsx', 'estado_bot.sqlite3', 'conhecimento_empresa.txt',
                 'navegacao.py', 'confiabilidade.py', 'INICIAR.bat']
        for nome in nomes:
            (self.raiz / nome).write_bytes(b'CONTEUDO PRESERVADO')
        original = self.arquivo.read_bytes()
        resultado = u.aplicar(self.arquivo)
        self.assertEqual(resultado['status'], 'atualizado')
        self.assertEqual(Path(resultado['backup']).read_bytes(), original)
        for nome in nomes:
            self.assertEqual((self.raiz / nome).read_bytes(), b'CONTEUDO PRESERVADO')
        self.assertFalse(list(self.raiz.glob('*.tmp')))

    def test_so_tres_funcoes_podem_diferir(self):
        novo, _ = u.gerar_atualizacao(BASE_SINTETICA, TRECHOS)
        before = ast.parse(BASE_SINTETICA)
        after = ast.parse(novo)
        def filtrar(tree):
            return [ast.dump(n) for n in tree.body if not (
                isinstance(n, ast.FunctionDef) and n.name in (u.NOVAS | u.SUBSTITUIDAS))]
        self.assertEqual(filtrar(before), filtrar(after))
        compile(novo, '<teste>', 'exec')

    def test_versao_diferente_recusada_sem_backup_ou_substituicao(self):
        original = (BASE_SINTETICA + '\n# mudanca posterior\n').encode()
        self.arquivo.write_bytes(original)
        with self.assertRaises(ValueError):
            u.aplicar(self.arquivo)
        self.assertEqual(self.arquivo.read_bytes(), original)
        self.assertFalse(list(self.raiz.glob('*.bak')))

    def test_reaplicar_e_idempotente(self):
        u.aplicar(self.arquivo)
        primeiro = self.arquivo.read_bytes()
        self.assertEqual(u.aplicar(self.arquivo)['status'], 'ja_atualizado')
        self.assertEqual(primeiro, self.arquivo.read_bytes())
        self.assertEqual(len(list(self.raiz.glob('*.bak'))), 1)

    def test_apenas_verificar_nao_grava_nada(self):
        original = self.arquivo.read_bytes()
        self.assertEqual(u.aplicar(self.arquivo, apenas_verificar=True)['status'], 'compativel')
        self.assertEqual(self.arquivo.read_bytes(), original)
        self.assertEqual(len(list(self.raiz.iterdir())), 1)

    def test_preserva_crlf_e_bom(self):
        original = b'\xef\xbb\xbf' + BASE_SINTETICA.replace('\n', '\r\n').encode()
        self.arquivo.write_bytes(original)
        resultado = u.aplicar(self.arquivo)
        novo = self.arquivo.read_bytes()
        self.assertTrue(novo.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n', novo.replace(b'\r\n', b''))
        self.assertEqual(Path(resultado['backup']).read_bytes(), original)

    def test_falha_gravacao_preserva_script_e_backup(self):
        original = self.arquivo.read_bytes()
        with patch.object(u.os, 'replace', side_effect=PermissionError('teste')):
            with self.assertRaises(PermissionError):
                u.aplicar(self.arquivo)
        self.assertEqual(self.arquivo.read_bytes(), original)
        self.assertEqual(list(self.raiz.glob('*.bak'))[0].read_bytes(), original)
        self.assertFalse(list(self.raiz.glob('*.tmp')))

    def test_edicao_concorrente_nao_e_sobrescrita(self):
        original = self.arquivo.read_bytes()
        def editar(*args):
            self.arquivo.write_bytes(original + b'# edicao do usuario\n')
        with patch.object(u.shutil, 'copymode', side_effect=editar):
            with self.assertRaises(RuntimeError):
                u.aplicar(self.arquivo)
        self.assertTrue(self.arquivo.read_bytes().endswith(b'# edicao do usuario\n'))
        self.assertFalse(list(self.raiz.glob('*.tmp')))

    def test_arquivo_inexistente_nao_cria_programa_vazio(self):
        with self.assertRaises(ValueError):
            u.aplicar(self.raiz / 'nao_existe.py')
        self.assertFalse((self.raiz / 'nao_existe.py').exists())

    def test_trecho_incompleto_recusado(self):
        with self.assertRaises(ValueError):
            u.gerar_atualizacao(BASE_SINTETICA, 'def executar_ciclo(driver, agenda):\n    pass\n')


@unittest.skipUnless(os.environ.get('POWER_STREAMING_FONTE_TESTE'),
                     'Teste privado opcional: indique POWER_STREAMING_FONTE_TESTE.')
class TestArquivoEnviado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fonte = Path(os.environ['POWER_STREAMING_FONTE_TESTE']).read_text(encoding='utf-8-sig')
        cls.novo, cls.alterado = u.gerar_atualizacao(cls.fonte, TRECHOS)

    def test_codigo_enviado_aceito_e_compila(self):
        self.assertTrue(self.alterado)
        compile(self.novo, '<bot atualizado>', 'exec')

    def test_todas_as_76_outras_funcoes_preservadas(self):
        antes = u._funcoes(ast.parse(self.fonte))
        depois = u._funcoes(ast.parse(self.novo))
        iguais = set(antes) - u.SUBSTITUIDAS
        self.assertEqual(len(iguais), 76)
        for nome in iguais:
            with self.subTest(funcao=nome):
                self.assertEqual(ast.dump(antes[nome]), ast.dump(depois[nome]))

    def test_mensagem_inicial_preservada_e_sem_telefone_no_nome(self):
        arvore = ast.parse(self.novo)
        funcs = [n for n in arvore.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('mensagem_apresentacao', 'gerar_mensagem_abordagem_fria')]
        ns = {}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), '<apresentacao>', 'exec'), ns)
        texto = ns['gerar_mensagem_abordagem_fria'](123456)
        for fragmento in ['IAgo', 'Power Streaming', 'bem-vindo', 'filmes', 'séries',
                          'Smart TV', 'TV Box', 'celular', 'cabe no seu bolso']:
            self.assertIn(fragmento, texto)
        self.assertNotIn('123456', texto)

    def test_modos_1_e_5_continuam_no_mesmo_agendador(self):
        antes, depois = ast.parse(self.fonte), ast.parse(self.novo)
        menu_antes, menu_depois = antes.body[-1], depois.body[-1]
        self.assertEqual(ast.dump(menu_antes), ast.dump(menu_depois))
        inicio = u._funcoes(depois)['iniciar_sistema']
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == 'executar_ciclo' for n in ast.walk(inicio)))

    def test_reproduz_tres_rotinas_seguidas_no_agendador_anterior(self):
        chamadas = []
        ns = {
            'time': SimpleNamespace(time=lambda: 1000),
            'random': SimpleNamespace(uniform=lambda *args: 360),
            'MINUTOS_MIN_ENTRE_ABORDAGENS_FRIAS': 5,
            'MINUTOS_MAX_ENTRE_ABORDAGENS_FRIAS': 7,
            'atender_entre_envios': lambda *a: chamadas.append('atendimento'),
            'processar_fila_acoes_web': lambda *a: None,
            'enviar_alertas_pendentes': lambda *a: None,
            'rodar_verificacoes_diarias': lambda *a, **kw: chamadas.append('diario'),
            'verificar_followups_teste_60min': lambda *a, **kw: chamadas.append('followup'),
            'processar_proximo_lead_frio': lambda *a: chamadas.append('frio'),
        }
        original = u._funcoes(ast.parse(self.fonte))['executar_ciclo']
        exec(compile(ast.Module(body=[original], type_ignores=[]), '<agendador anterior>', 'exec'), ns)
        ns['executar_ciclo'](object(), {'diario': 900, 'followup': 900, 'frio': 900, 'status': 2000})
        self.assertEqual(chamadas, ['atendimento', 'diario', 'followup', 'frio'])

    def ambiente_base_fria(self, quantidade=4):
        estado = EstadoFake()
        rows = [[SimpleNamespace(value=v) for v in
                 ['Teste ' + str(i), 'contato-sintetico-' + str(i), 'Lead Frio'] + [''] * 14]
                for i in range(quantidade)]
        ws = SimpleNamespace(iter_rows=lambda **kw: iter(rows))
        def status(telefone, valor, nome=None):
            next(r for r in rows if r[1].value == telefone)[2].value = valor
        def marcar(telefone, nome=None):
            next(r for r in rows if r[1].value == telefone)[16].value = 'CONFIRMADO'
        ns = {
            'time': SimpleNamespace(time=lambda: 1000),
            'estado_bot': lambda: estado,
            'abrir_planilha': lambda: SimpleNamespace(active=ws),
            'normalizar_telefone_br': lambda t: str(t) if t else '',
            'impedido': lambda t, n, r: r[12].value == 'nao abordar',
            'abrir_destinatario': Mock(return_value=('caixa', False)),
            'blocos_mensagens': Mock(return_value=[]),
            'direcao': lambda bloco: bloco,
            'capturar_chat_atual': Mock(),
            'marcar_status': Mock(side_effect=status),
            'marcar_abordagem_fria_feita': Mock(side_effect=marcar),
            'enviar_pela_caixa_e_confirmar': Mock(return_value=True),
        }
        nomes = {'obter_proximo_lead_frio', 'contato_com_pendencia',
                 'processar_proximo_lead_frio', 'mensagem_apresentacao',
                 'gerar_mensagem_abordagem_fria'}
        funcs = [n for n in ast.parse(self.novo).body
                 if isinstance(n, ast.FunctionDef) and n.name in nomes]
        exec(compile(ast.Module(body=funcs, type_ignores=[]), '<base fria isolada>', 'exec'), ns)
        return ns, rows, estado

    def test_base_de_4000_aborda_so_um_por_chamada(self):
        ns, rows, _ = self.ambiente_base_fria(4000)
        with redirect_stdout(io.StringIO()):
            ns['processar_proximo_lead_frio']('navegador-simulado')
        self.assertEqual(ns['abrir_destinatario'].call_count, 1)
        self.assertEqual(ns['enviar_pela_caixa_e_confirmar'].call_count, 1)
        self.assertEqual(sum(r[2].value == 'Lead' for r in rows), 1)
        texto = ns['enviar_pela_caixa_e_confirmar'].call_args.args[2]
        self.assertIn('Sou o IAgo', texto)

    def test_proxima_chamada_avanca_sem_repetir_confirmado(self):
        ns, rows, _ = self.ambiente_base_fria()
        with redirect_stdout(io.StringIO()):
            ns['processar_proximo_lead_frio']('navegador-simulado')
            ns['processar_proximo_lead_frio']('navegador-simulado')
        self.assertEqual([r[2].value for r in rows], ['Lead', 'Lead', 'Lead Frio', 'Lead Frio'])
        chamados = ns['abrir_destinatario'].call_args_list
        self.assertNotEqual(chamados[0].args[1], chamados[1].args[1])

    def test_sem_confirmacao_nao_promove_nem_marca_abordado(self):
        ns, rows, _ = self.ambiente_base_fria()
        ns['enviar_pela_caixa_e_confirmar'].return_value = False
        ns['processar_proximo_lead_frio']('navegador-simulado')
        self.assertEqual(rows[0][2].value, 'Lead Frio')
        self.assertEqual(rows[0][16].value, '')
        ns['marcar_status'].assert_not_called()
        ns['marcar_abordagem_fria_feita'].assert_not_called()

    def test_resposta_encontrada_ao_abrir_nao_recebe_propaganda(self):
        ns, _, _ = self.ambiente_base_fria()
        ns['blocos_mensagens'].return_value = ['entrada']
        ns['processar_proximo_lead_frio']('navegador-simulado')
        ns['capturar_chat_atual'].assert_called_once()
        ns['enviar_pela_caixa_e_confirmar'].assert_not_called()

    def test_bloqueado_duplicado_pendente_e_ja_abordado_preservados(self):
        ns, rows, estado = self.ambiente_base_fria(7)
        rows[0][12].value = 'nao abordar'
        rows[1][1].value = rows[2][1].value
        estado.set('entrada:x', {'telefone': rows[3][1].value, 'status': 'pendente', 'retry': 99999})
        rows[4][16].value = 'CONFIRMADO ANTES'
        rows[5][2].value = 'Cliente'
        self.assertEqual(ns['obter_proximo_lead_frio']()[1], rows[6][1].value)

    def test_sem_elegiveis_nao_abre_conversa(self):
        ns, rows, _ = self.ambiente_base_fria()
        for r in rows:
            r[2].value = 'Cliente'
        ns['processar_proximo_lead_frio']('navegador-simulado')
        ns['abrir_destinatario'].assert_not_called()
        ns['enviar_pela_caixa_e_confirmar'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
