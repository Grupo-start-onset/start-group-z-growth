# ==================================================================
# notificar_pedidos.py
# Compara os pedidos de compra (POs) do dados_vendor.json com a ultima
# rodada e manda email pro(s) destinatario(s) de cada conta quando um
# PO NOVO aparece (ou seja: a Amazon emitiu um pedido pra gente desde
# a ultima vez que isso rodou -- nao tem relacao com "produto chegou
# fisicamente no CD", que e outro dado, dataReceb).
#
# Estado (quais PO ja foram notificados) fica em
# dados_raw/pedidos_notificados.json -- esse arquivo E COMMITADO no
# repo pra persistir entre execucoes do GitHub Actions (que comeca do
# zero a cada run). Na primeira execucao (arquivo nao existe), marca
# TODOS os PO atuais como ja notificados e NAO manda email nenhum --
# so a partir da segunda rodada e que PO novo vira notificacao.
#
# Destinatarios: DESTINATARIOS_CONTA abaixo. Hoje, fase de teste, todas
# as contas apontam pro mesmo email (comercial@onsetsell.com) -- depois
# e so trocar pelo email de cada cliente.
#
# Precisa de GMAIL_USER e GMAIL_APP_PASSWORD no .env (local) ou
# Secrets do GitHub Actions. Roda DEPOIS do transformar_vendor.py
# (precisa do bloco `pedidos` atualizado) e antes do publicar_github.py
# (esse ultimo nao mexe no dados_raw/, entao o commit do estado de
# notificacao e feito pelo proprio script, no final).
#
# Uso: python scripts/notificar_pedidos.py
#      python scripts/notificar_pedidos.py --teste              (manda um email de teste generico e sai, sem mexer no estado)
#      python scripts/notificar_pedidos.py --preview <conta>    (manda o email no formato REAL, com os
#                                                                 PO mais recentes de verdade dessa conta,
#                                                                 marcado [PREVIA] no assunto -- NAO mexe
#                                                                 no estado de notificados, so serve pra
#                                                                 ver o formato que o cliente vai receber)
# ==================================================================

import os, sys, json, smtplib, ssl, subprocess, tempfile, shutil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from gerar_pedido_xlsx import gerar_xlsx_pedido

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
ARQUIVO_VENDOR = os.path.join(RAIZ, 'dados_vendor.json')
ARQUIVO_ESTADO = os.path.join(RAIZ, 'dados_raw', 'pedidos_notificados.json')

CONTA_NOME = {
    'alfa_jf': 'ALFA JF', 'blidshop': 'Blid Shop', 'conta3': 'Petclean BR',
    'ozitp': 'OZITP', 'jolitex': 'Jolitex', 'balboa': 'Balboa', 'riomaster': 'BR - Rio Master',
    'plastpet': 'Pet Factory Brazil Industria Ltda',
}

# FASE DE TESTE: todas as contas mandam pro mesmo email. Pra ligar pro
# cliente de verdade, troca o valor da conta pelo(s) email(s) dela --
# pode ser uma string ou uma lista de strings (varios destinatarios).
EMAIL_TESTE = 'comercial@onsetsell.com'
DESTINATARIOS_CONTA = {chave: EMAIL_TESTE for chave in CONTA_NOME}


def carregar_estado():
    if os.path.exists(ARQUIVO_ESTADO):
        return json.load(open(ARQUIVO_ESTADO, encoding='utf-8'))
    return {}


def salvar_estado(estado):
    os.makedirs(os.path.dirname(ARQUIVO_ESTADO), exist_ok=True)
    with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2, sort_keys=True)


def destinatarios(lista_ou_str):
    if isinstance(lista_ou_str, str):
        return [lista_ou_str]
    return list(lista_ou_str)


def _fmt_data_curta(iso):
    if not iso:
        return '—'
    return iso[:10][8:10] + '/' + iso[5:7] + '/' + iso[:4]


def _num_br(v):
    return f'{v:,.0f}'.replace(',', '.')


def montar_corpo(conta_nome, pos_novos):
    linhas = [f'{len(pos_novos)} pedido(s) de compra novo(s) para {conta_nome}:\n']
    total_un = 0
    for p in pos_novos:
        un = (p.get('tot') or {}).get('pedido', 0)
        total_un += un
        data = _fmt_data_curta(p.get('data'))
        janela = (f"{_fmt_data_curta(p.get('janelaIni'))} a {_fmt_data_curta(p.get('janelaFim'))}"
                  if p.get('janelaFim') else '—')
        linhas.append(f"  - PO {p['po']} | emitido em {data} | {_num_br(un)} unidade(s) pedidas | "
                       f"{len((p.get('itens') or []))} item(ns)")
        linhas.append(f"      >>> JANELA DE ENTREGA: {janela} <<<")
    linhas.append(f'\nTotal: {_num_br(total_un)} unidade(s) pedidas nesses pedidos.')
    linhas.append('\nO detalhamento completo de cada pedido (itens, custos, janela de entrega) esta')
    linhas.append('nos arquivos Excel em anexo, um por pedido.')
    linhas.append('\n--\nEnviado automaticamente pelo pipeline START Vendor Analytics.')
    return '\n'.join(linhas)


def gerar_anexos(pasta_tmp, chave, conta_nome, catalogo, pos_novos):
    """Gera um .xlsx por PO em pasta_tmp e devolve a lista de caminhos."""
    caminhos = []
    for p in pos_novos:
        caminho = os.path.join(pasta_tmp, f"Pedido_{p['po']}_{chave}.xlsx")
        gerar_xlsx_pedido(chave, conta_nome, p, catalogo, caminho)
        caminhos.append(caminho)
    return caminhos


def enviar_email(destinatarios_lista, assunto, corpo, anexos=None):
    user = os.environ.get('GMAIL_USER')
    pw = os.environ.get('GMAIL_APP_PASSWORD')
    if not user or not pw:
        raise RuntimeError('GMAIL_USER / GMAIL_APP_PASSWORD nao configurados (.env ou Secrets do GitHub Actions).')

    msg = MIMEMultipart()
    msg['Subject'] = assunto
    msg['From'] = user
    msg['To'] = ', '.join(destinatarios_lista)
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

    for caminho in (anexos or []):
        with open(caminho, 'rb') as f:
            parte = MIMEApplication(f.read(), _subtype='xlsx')
        parte.add_header('Content-Disposition', 'attachment', filename=os.path.basename(caminho))
        msg.attach(parte)

    ctx = ssl.create_default_context()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(user, pw)
        s.send_message(msg)


def git(args):
    return subprocess.run(['git', '-C', RAIZ] + args, capture_output=True, text=True)


def commitar_estado():
    git(['add', 'dados_raw/pedidos_notificados.json'])
    r = git(['commit', '-m', f'Atualiza estado de notificacao de pedidos — {datetime.now().strftime("%Y-%m-%d %H:%M")}'])
    if 'nothing to commit' in (r.stdout + r.stderr):
        print('[estado] nada mudou no arquivo de notificados -- nada a commitar.')
        return
    git(['push'])
    print('[estado] dados_raw/pedidos_notificados.json commitado e enviado.')


def main():
    args = sys.argv[1:]
    teste = '--teste' in args

    if teste:
        enviar_email([EMAIL_TESTE], 'Teste - alertas de pedidos START',
                     'Este e um email de teste do notificar_pedidos.py. Se voce recebeu isso, o envio esta funcionando.')
        print(f'Email de teste enviado para {EMAIL_TESTE}.')
        return

    if '--preview' in args:
        idx = args.index('--preview')
        chave = args[idx + 1] if idx + 1 < len(args) else None
        if not chave or chave not in CONTA_NOME:
            print(f"[erro] uso: --preview <conta>, onde <conta> e uma de: {', '.join(CONTA_NOME)}")
            sys.exit(1)
        contas = json.load(open(ARQUIVO_VENDOR, encoding='utf-8'))
        pedidos = [p for p in (contas.get(chave, {}).get('pedidos') or []) if p.get('po') and p.get('data')]
        pedidos.sort(key=lambda p: p['data'], reverse=True)
        amostra = pedidos[:3]
        if not amostra:
            print(f'[erro] nenhum pedido com data encontrado para {chave}.')
            sys.exit(1)
        conta_nome = CONTA_NOME[chave]
        assunto = f'{len(amostra)} pedido(s) de compra novo(s) — {conta_nome} [PREVIA]'
        corpo = montar_corpo(conta_nome, amostra)
        dest = destinatarios(DESTINATARIOS_CONTA.get(chave, EMAIL_TESTE))
        pasta_tmp = tempfile.mkdtemp(prefix='pedidos_preview_')
        try:
            anexos = gerar_anexos(pasta_tmp, chave, conta_nome, contas.get(chave, {}).get('catalogo'), amostra)
            enviar_email(dest, assunto, corpo, anexos)
        finally:
            shutil.rmtree(pasta_tmp, ignore_errors=True)
        print(f'[preview] email enviado para {dest} com {len(amostra)} pedido(s) reais de {conta_nome} ({len(amostra)} anexo(s)).')
        print(corpo)
        return

    if not os.path.exists(ARQUIVO_VENDOR):
        print(f'[erro] {ARQUIVO_VENDOR} nao encontrado -- rode transformar_vendor.py primeiro.')
        sys.exit(1)
    contas = json.load(open(ARQUIVO_VENDOR, encoding='utf-8'))
    estado = carregar_estado()
    primeira_vez = not os.path.exists(ARQUIVO_ESTADO)

    # destinatario -> lista de (conta_nome, [pos novos])
    por_destinatario = {}
    algo_novo = False

    for chave, conta_nome in CONTA_NOME.items():
        if chave not in contas:
            continue
        ja_notificados = set(estado.get(chave, []))
        pedidos = contas[chave].get('pedidos') or []
        pedidos_com_po = [p for p in pedidos if p.get('po') and p.get('data')]

        novos = [p for p in pedidos_com_po if p['po'] not in ja_notificados]
        estado[chave] = sorted({p['po'] for p in pedidos_com_po} | ja_notificados)

        if novos and not primeira_vez:
            algo_novo = True
            for dest in destinatarios(DESTINATARIOS_CONTA.get(chave, EMAIL_TESTE)):
                por_destinatario.setdefault(dest, []).append((chave, conta_nome, novos))
            print(f'[{chave}] {len(novos)} pedido(s) novo(s) -- notificando {DESTINATARIOS_CONTA.get(chave)}')
        elif novos and primeira_vez:
            print(f'[{chave}] primeira execucao -- {len(novos)} pedido(s) existente(s) marcado(s) como ja notificado(s), sem email.')
        else:
            print(f'[{chave}] nenhum pedido novo.')

    if primeira_vez:
        salvar_estado(estado)
        commitar_estado()
        print('\nEstado inicial gravado. A partir da proxima execucao, PO novo vira email.')
        return

    if not algo_novo:
        print('\nNenhum pedido novo em nenhuma conta -- nenhum email enviado.')
        salvar_estado(estado)  # idempotente, mas garante consistencia se algo mudou sem gerar "novo"
        commitar_estado()
        return

    for dest, blocos in por_destinatario.items():
        total_pos = sum(len(novos) for _, nome, novos in blocos)
        assunto = f'{total_pos} pedido(s) de compra novo(s) — ' + ', '.join(nome for _, nome, _ in blocos)
        corpo = '\n\n'.join(montar_corpo(nome, novos) for _, nome, novos in blocos)
        pasta_tmp = tempfile.mkdtemp(prefix='pedidos_notif_')
        try:
            anexos = []
            for chave, nome, novos in blocos:
                anexos += gerar_anexos(pasta_tmp, chave, nome, contas.get(chave, {}).get('catalogo'), novos)
            enviar_email([dest], assunto, corpo, anexos)
            print(f'[email] enviado para {dest}: {assunto} ({len(anexos)} anexo(s))')
        except Exception as e:
            print(f'[ERRO] falha ao enviar para {dest}: {e}')
        finally:
            shutil.rmtree(pasta_tmp, ignore_errors=True)

    salvar_estado(estado)
    commitar_estado()


if __name__ == '__main__':
    main()
