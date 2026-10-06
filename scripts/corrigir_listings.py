# ==================================================================
# corrigir_listings.py
# Envia correcoes de atributos (Listings Items API, patch_listings_item)
# a partir da aba "Corrigível via API" de correcoes_propostas.xlsx, depois
# de alguem preencher a coluna "Valor correto (preencher)".
#
# ESCOPO DESTA V1: so o codigo 18448 (atributos principais faltando), que
# e o maior grupo (455 issues) e o unico onde o nome do atributo vem
# escrito na propria mensagem da Amazon ("Faltam alguns atributos
# principais em seu envio: container.type, product_benefit, ..."). Os
# outros codigos (18002, 99022, 90244, 99016, 100893) tem formato de
# valor mais especifico por atributo/categoria e ficam pra uma proxima
# versao.
#
# FORMATO da coluna "Valor correto (preencher)", por linha da planilha:
#   um_valor_so                          -> usa esse valor pra TODOS os
#                                            atributos faltando dessa linha
#   atributo1=valor1;atributo2=valor2    -> um valor por atributo
#
# SEGURANCA:
#   - Por padrao roda em modo SIMULACAO (--dry-run, e o padrao): so
#     mostra o que seria enviado, NADA e enviado pra Amazon.
#   - Envio de verdade exige --enviar E --conta <chave> (uma conta por
#     vez, nunca todas de uma vez sem querer) E --confirmar.
#   - Cada linha e enviada e logada separadamente -- erro numa linha nao
#     para as outras.
#   - Log completo (pedido + resposta) em correcoes_enviadas_<conta>_<data>.json
#
# Uso:
#   python scripts/corrigir_listings.py                                  # simulacao, todas as contas
#   python scripts/corrigir_listings.py --conta jolitex                  # simulacao, so jolitex
#   python scripts/corrigir_listings.py --conta jolitex --enviar --confirmar   # envia de verdade
# ==================================================================

import os, sys, json, re, time, argparse
from datetime import datetime
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from colab_shim import drive, userdata

try:
    from sp_api.api import ListingsItems
    from sp_api.base import Marketplaces
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import ListingsItems
    from sp_api.base import Marketplaces

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PLANILHA = os.path.join(RAIZ, 'correcoes_propostas.xlsx')
MARKETPLACE = Marketplaces.BR
MARKETPLACE_ID = 'A2Q3Y263D00KWC'

LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')

CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'secret': 'SP_API_REFRESH_TOKEN_ALFAJF',   'seller_id': '76I78'},
    'blidshop':  {'nome': 'Blid Shop',       'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP', 'seller_id': 'UM8O1'},
    'petclean':  {'nome': 'Petclean BR',     'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN', 'seller_id': 'A470C'},
    'ozitp':     {'nome': 'OZITP',           'secret': 'SP_API_REFRESH_TOKEN_OZITP',    'seller_id': 'OZITV'},
    'jolitex':   {'nome': 'Jolitex',         'secret': 'SP_API_REFRESH_TOKEN_JOLITEX',  'seller_id': 'R88OM'},
    'balboa':    {'nome': 'Balboa',          'secret': 'SP_API_REFRESH_TOKEN_BALBOA',   'seller_id': '6R8TT'},
    'riomaster': {'nome': 'BR - Rio Master', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER','seller_id': 'RD8QP'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET', 'seller_id': 'SY933'},
    'wiwu':      {'nome': 'WIWU', 'secret': 'SP_API_REFRESH_TOKEN_WIWU', 'seller_id': '4E8ND'},
    'petiko':    {'nome': 'PETIKO', 'secret': 'SP_API_REFRESH_TOKEN_PETIKO', 'seller_id': 'YM9CK'},
}
# nome de exibicao (como sai na planilha) -> chave interna da conta
NOME_PARA_CHAVE = {cfg['nome']: chave for chave, cfg in CONTAS_CONFIG.items()}

RE_ATRIBUTOS_18448 = re.compile(r'envio:\s*(.*?)\.\s*A falta')


def credenciais(chave):
    refresh = userdata.get(CONTAS_CONFIG[chave]['secret'])
    if not (refresh and LWA_CLIENT_ID and LWA_CLIENT_SECRET):
        return None
    return dict(refresh_token=refresh, lwa_app_id=LWA_CLIENT_ID, lwa_client_secret=LWA_CLIENT_SECRET)


def ler_planilha_aprovadas(conta_filtro=None):
    wb = openpyxl.load_workbook(PLANILHA, data_only=True)
    if 'Corrigível via API' not in wb.sheetnames:
        raise RuntimeError('Aba "Corrigível via API" não encontrada -- rode classificar_correcoes.py primeiro.')
    ws = wb['Corrigível via API']
    cabecalho = [c.value for c in ws[1]]
    idx = {nome: i for i, nome in enumerate(cabecalho)}

    linhas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[idx['ASIN']]:
            continue
        valor_correto = row[idx['Valor correto (preencher)']]
        if not valor_correto or not str(valor_correto).strip():
            continue  # linha ainda não aprovada/preenchida -- pula
        nome_conta = row[idx['Conta']]
        chave = NOME_PARA_CHAVE.get(nome_conta)
        if not chave:
            print(f'  [aviso] conta "{nome_conta}" não reconhecida -- pulando linha (ASIN {row[idx["ASIN"]]})')
            continue
        if conta_filtro and chave != conta_filtro:
            continue
        if str(row[idx['Código']]) != '18448':
            print(f'  [aviso] código {row[idx["Código"]]} fora do escopo desta v1 (só 18448) -- pulando ASIN {row[idx["ASIN"]]}')
            continue
        linhas.append({
            'conta': chave, 'nome_conta': nome_conta,
            'asin': row[idx['ASIN']], 'sku': row[idx['SKU']],
            'produto': row[idx['Produto']], 'mensagem': row[idx['Mensagem da Amazon']],
            'valor_correto': str(valor_correto).strip(),
        })
    return linhas


def montar_patches(linha):
    m = RE_ATRIBUTOS_18448.search(linha['mensagem'] or '')
    if not m:
        return None, 'não foi possível extrair os nomes dos atributos da mensagem'
    atributos = [a.strip() for a in m.group(1).split(',') if a.strip()]

    valor_bruto = linha['valor_correto']
    valores = {}
    if '=' in valor_bruto:
        for par in valor_bruto.split(';'):
            par = par.strip()
            if not par:
                continue
            if '=' not in par:
                return None, f'formato inválido em "Valor correto": "{par}" (esperado atributo=valor)'
            k, v = par.split('=', 1)
            valores[k.strip()] = v.strip()
    else:
        valores = {a: valor_bruto for a in atributos}

    faltando = [a for a in atributos if a not in valores]
    if faltando:
        return None, f'faltam valores para: {", ".join(faltando)} (atributos da issue: {", ".join(atributos)})'

    patches = [
        {'op': 'replace', 'path': f'/attributes/{attr}', 'value': [{'value': valores[attr]}]}
        for attr in atributos
    ]
    return patches, None


def descobrir_product_type(api, seller_id, sku):
    resp = api.get_listings_item(seller_id, sku, marketplaceIds=[MARKETPLACE_ID], includedData=['summaries'])
    summaries = (resp.payload or {}).get('summaries', [])
    if summaries:
        return summaries[0].get('productType')
    return None


def processar_conta(chave, linhas_conta, enviar, log):
    cfg = CONTAS_CONFIG[chave]
    cred = credenciais(chave)
    if not cred:
        print(f'  [pulando "{chave}"] credenciais incompletas')
        return

    api = ListingsItems(credentials=cred, marketplace=MARKETPLACE)
    seller_id = cfg['seller_id']

    print(f'\n=== {cfg["nome"]} ({len(linhas_conta)} linha(s) aprovada(s), código 18448) ===')
    for linha in linhas_conta:
        patches, erro = montar_patches(linha)
        item = {
            'conta': chave, 'asin': linha['asin'], 'sku': linha['sku'], 'produto': linha['produto'],
            'valor_correto_informado': linha['valor_correto'],
        }
        if erro:
            print(f'  [PULADO] {linha["asin"]} ({linha["sku"]}): {erro}')
            item.update({'status': 'PULADO', 'erro': erro})
            log.append(item)
            continue

        try:
            product_type = descobrir_product_type(api, seller_id, linha['sku'])
        except Exception as e:
            print(f'  [ERRO ao buscar productType] {linha["asin"]} ({linha["sku"]}): {e}')
            item.update({'status': 'ERRO_PRODUCT_TYPE', 'erro': str(e)})
            log.append(item)
            continue

        if not product_type:
            print(f'  [PULADO] {linha["asin"]} ({linha["sku"]}): não achei productType')
            item.update({'status': 'PULADO', 'erro': 'productType não encontrado'})
            log.append(item)
            continue

        body = {'productType': product_type, 'patches': patches}
        item['payload'] = body

        if not enviar:
            print(f'  [SIMULAÇÃO] {linha["asin"]} ({linha["sku"]}, {product_type}):')
            print(f'      {json.dumps(patches, ensure_ascii=False)}')
            item['status'] = 'SIMULADO'
            log.append(item)
            continue

        try:
            resp = api.patch_listings_item(
                seller_id, linha['sku'],
                marketplaceIds=[MARKETPLACE_ID], body=body, issueLocale='pt_BR',
            )
            payload = resp.payload or {}
            status = payload.get('status', '?')
            issues = payload.get('issues', [])
            print(f'  [{status}] {linha["asin"]} ({linha["sku"]}) -- {len(issues)} issue(s) na resposta')
            item.update({'status': status, 'resposta_issues': issues})
        except Exception as e:
            print(f'  [FALHOU AO ENVIAR] {linha["asin"]} ({linha["sku"]}): {e}')
            item.update({'status': 'FALHOU', 'erro': str(e)})
        log.append(item)
        time.sleep(0.5)  # 5 req/s de limite (usage plan da patch_listings_item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--conta', help='só processa essa conta (chave interna, ex.: jolitex)')
    ap.add_argument('--enviar', action='store_true', help='envia de verdade (padrão: só simula)')
    ap.add_argument('--confirmar', action='store_true', help='obrigatório junto com --enviar')
    args = ap.parse_args()

    if args.enviar and not args.confirmar:
        print('Para enviar de verdade, use --enviar junto com --confirmar.')
        sys.exit(1)
    if args.enviar and not args.conta:
        print('Para enviar de verdade, use também --conta <chave> -- uma conta por vez.')
        sys.exit(1)

    if not os.path.exists(PLANILHA):
        print(f'Não achei {PLANILHA} -- rode scripts/classificar_correcoes.py primeiro.')
        sys.exit(1)

    linhas = ler_planilha_aprovadas(conta_filtro=args.conta)
    if not linhas:
        print('Nenhuma linha aprovada encontrada (coluna "Valor correto (preencher)" vazia, ou fora do escopo desta v1).')
        return

    por_conta = {}
    for l in linhas:
        por_conta.setdefault(l['conta'], []).append(l)

    modo = 'ENVIO REAL' if args.enviar else 'SIMULAÇÃO (nada será enviado)'
    print(f'Modo: {modo}\n')

    log = []
    for chave, linhas_conta in por_conta.items():
        processar_conta(chave, linhas_conta, enviar=args.enviar, log=log)

    if args.enviar:
        agora = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        caminho_log = os.path.join(RAIZ, f'correcoes_enviadas_{args.conta}_{agora}.json')
        with open(caminho_log, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f'\nLog salvo: {caminho_log}')


if __name__ == '__main__':
    main()
