"""Atualizacao incremental, com validacao da origem e backup do script.

Nao importa o bot, nao abre o WhatsApp e nao altera planilha/banco/configuracao.
"""
import argparse
import ast
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


VERSAO = '2026.09.03-intercalacao.1'
SHA_BASE = '3a822a5b2440794be12fbdc259f8442186a90883ef7c012f826dd0101de90532'
NOVAS = {'ha_atendimento_pronto', 'informar_status_intercalacao'}
SUBSTITUIDAS = {'executar_ciclo'}
TRECHOS = Path(__file__).with_name('funcoes_intercaladas.py')


def normalizar(texto):
    return texto.replace('\r\n', '\n')


def assinatura(texto):
    return hashlib.sha256(normalizar(texto).encode('utf-8')).hexdigest()


def _funcoes(arvore):
    return {n.name: n for n in arvore.body if isinstance(n, ast.FunctionDef)}


def gerar_atualizacao(texto, trechos):
    """Retorna (codigo, alterado), recusando uma base diferente da revisada."""
    texto, trechos = normalizar(texto), normalizar(trechos)
    antes, payload = ast.parse(texto), ast.parse(trechos)
    funcoes, novas_funcoes = _funcoes(antes), _funcoes(payload)
    esperadas = NOVAS | SUBSTITUIDAS
    if set(novas_funcoes) != esperadas:
        raise ValueError('Pacote incompleto: os trechos da atualizacao nao conferem.')
    if all(nome in funcoes and ast.dump(funcoes[nome]) == ast.dump(novas_funcoes[nome])
           for nome in esperadas):
        return texto, False
    if assinatura(texto) != SHA_BASE:
        raise ValueError('Este arquivo e diferente da versao enviada para revisao. '
                         'Nada foi substituido. Envie o atendimento_whatsapp.py atual para adaptar a atualizacao.')
    if set(funcoes) & NOVAS or not SUBSTITUIDAS <= set(funcoes):
        raise ValueError('Estrutura do programa inesperada; atualizacao cancelada.')
    alvo = funcoes['executar_ciclo']
    linhas = texto.splitlines(keepends=True)
    partes = [ast.get_source_segment(trechos, n) for n in payload.body
              if isinstance(n, ast.FunctionDef)]
    linhas[alvo.lineno - 1:alvo.end_lineno] = ['\n\n\n'.join(partes) + '\n']
    resultado = ''.join(linhas)
    depois = ast.parse(resultado)
    # Protecao estrutural: nenhuma outra funcao, classe, import, configuracao
    # ou instrucao do menu pode mudar nesta atualizacao.
    def fora_da_alteracao(arvore):
        return [ast.dump(n) for n in arvore.body
                if not (isinstance(n, ast.FunctionDef) and n.name in esperadas)]
    if fora_da_alteracao(antes) != fora_da_alteracao(depois):
        raise ValueError('A verificacao de preservacao falhou; nada sera substituido.')
    compile(resultado, 'atendimento_whatsapp.py', 'exec')
    return resultado, True


def aplicar(arquivo, apenas_verificar=False):
    arquivo = Path(arquivo).absolute()
    if arquivo.is_symlink() or not arquivo.is_file():
        raise ValueError('Selecione o arquivo atendimento_whatsapp.py real, nao um atalho.')
    original = arquivo.read_bytes()
    texto = original.decode('utf-8-sig')
    novo, alterado = gerar_atualizacao(texto, TRECHOS.read_text(encoding='utf-8'))
    if not alterado:
        return {'status': 'ja_atualizado', 'arquivo': str(arquivo)}
    if apenas_verificar:
        return {'status': 'compativel', 'arquivo': str(arquivo)}
    # Mantem o estilo de quebra de linha e a presenca de BOM do arquivo original.
    quebra = '\r\n' if b'\r\n' in original else '\n'
    bytes_novos = novo.replace('\n', quebra).encode('utf-8')
    if original.startswith(b'\xef\xbb\xbf'):
        bytes_novos = b'\xef\xbb\xbf' + bytes_novos
    backup = arquivo.with_name(arquivo.name + '.antes_intercalacao_' +
                              datetime.now().strftime('%Y%m%d_%H%M%S') + '_' +
                              uuid.uuid4().hex[:8] + '.bak')
    temporario = None
    try:
        with backup.open('xb') as saida:
            saida.write(original)
            saida.flush()
            os.fsync(saida.fileno())
        shutil.copystat(arquivo, backup)
        with tempfile.NamedTemporaryFile(prefix='intercalacao_', suffix='.tmp',
                                         dir=arquivo.parent, delete=False) as saida:
            temporario = Path(saida.name)
            saida.write(bytes_novos)
            saida.flush()
            os.fsync(saida.fileno())
        shutil.copymode(arquivo, temporario)
        if arquivo.read_bytes() != original:
            raise RuntimeError('O script mudou durante a atualizacao. Operacao cancelada; backup preservado.')
        os.replace(temporario, arquivo)
        temporario = None
        if arquivo.read_bytes() != bytes_novos:
            raise RuntimeError('Nao foi possivel confirmar os bytes finais. Nao inicie o bot; use o backup.')
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()
    return {'status': 'atualizado', 'arquivo': str(arquivo), 'backup': str(backup),
            'sha256': hashlib.sha256(bytes_novos).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arquivo', default=r'C:\power_streaming\atendimento_whatsapp.py')
    parser.add_argument('--verificar', action='store_true', help='Apenas verifica; nao grava nada.')
    args = parser.parse_args()
    try:
        resultado = aplicar(args.arquivo, apenas_verificar=True)
        if args.verificar or resultado['status'] == 'ja_atualizado':
            print('Resultado:', resultado['status'])
            print('Arquivo:', resultado['arquivo'])
            return 0
        print('Power Streaming - atualizacao', VERSAO)
        print('Arquivo:', resultado['arquivo'])
        print('Pare o bot com Ctrl+C antes de continuar. Feche todas as instancias.')
        print('Apenas o script sera atualizado; planilha, banco e modulos auxiliares ficam intactos.')
        if input('Com o bot parado, digite ATUALIZAR e pressione Enter: ').strip() != 'ATUALIZAR':
            print('Cancelado. Nenhum arquivo alterado.')
            return 0
        resultado = aplicar(args.arquivo)
        print('Resultado:', resultado['status'])
        if 'backup' in resultado:
            print('Copia de seguranca:', resultado['backup'])
        print('Inicie pelo procedimento habitual e escolha a opcao 1 ou 5.')
        return 0
    except (OSError, ValueError, RuntimeError, SyntaxError, UnicodeError, EOFError) as exc:
        print('ATUALIZACAO NAO CONCLUIDA:', exc)
        print('Nao apague seus dados. Confira o caminho e a versao antes de tentar novamente.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
