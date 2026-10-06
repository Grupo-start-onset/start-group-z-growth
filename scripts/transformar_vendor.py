"""
transformar_vendor.py
======================
Célula final do notebook Colab do projeto START Vendor Analytics.

Lê os JSONs brutos de cada conta em
  START_Vendor_Analytics/<conta>/raw/*.json
e gera um único arquivo `dados_vendor.json` no formato do objeto CONTAS
(ver schema_dadosx.md no Project Knowledge), pronto para ser consumido
via fetch() pelo dashboard_base.html — sem precisar embutir o dado no HTML
nem reenviar nada para o Claude.

Rodar como célula final, depois de todas as células de captura da API.
Requer apenas biblioteca padrão (json, glob, os, collections, datetime).

Histórico:
  25/09/2026 — novo bloco `qualidadeListings`, carregado de
  qualidade_listings.json (gerado por capturar_qualidade_listings.py via
  Listings Items API, search_listings_items). Por ASIN: status da listagem,
  se está suprimida (LISTING_SUPPRESSED), erros e avisos reportados pela
  própria Amazon. Independente do bloco `qualidade` (CDQ antigo, que
  dependia de 4 capturas nunca implementadas — imagens_completas,
  relationships, aplus_content_massa — e do calcular_qualidade_catalogo.py
  que as combinava). Os dois blocos convivem; `qualidadeListings` é o que
  tem dado real disponível hoje.
  22/09/2026 — sell-in reescrito: lê pedidos_*.json + status_pedidos_*.json
  (gerados por capturar_pedidos.py) no lugar do antigo
  purchase_orders_60dias.json; dedupe por purchaseOrderNumber; `rej` agora
  vem de acknowledgementStatusDetails[] (antes ficava sempre 0); campos novos
  de quantidade pedida/cancelada/recebida, sellinRecebidoMes e atrasados.
  Rio Master incluída no CONTAS_CONFIG.
  22/09/2026 (3) — `pedido` passa a ser a quantidade ORIGINAL (1º registro de
  orderedQuantityDetails); o nível de cima já vem líquido de cancelamento.
  Cancelado = original - atual. Novo `confValido` = min(aceito, pedido atual):
  base de custo, pendente e atrasados (a Amazon cancela depois do aceite).
  Recebido sem lastReceiveDate usa lastUpdatedDate do PO.
  Aceito/rejeitado sempre pela soma de acknowledgementStatusDetails[]; o
  acceptedQuantity do nível de cima vem inconsistente em parte dos itens.
  22/09/2026 (2) — bloco `pedidos`: lista de POs com data, número, status,
  janela de entrega e itens (quantidades, custo, recebimento) por PO.
"""

import json, glob, os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Config — ajustar aqui se a estrutura de pastas ou os nomes das contas mudarem
# ---------------------------------------------------------------------------

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))

CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',   'pasta': 'alfa_jf/raw'},
    'blidshop':  {'nome': 'Blid Shop', 'pasta': 'blidshop/raw'},
    # AVISO: pasta física é "petclean/raw", não "conta3/raw" -- mantive a chave
    # "conta3" porque é como o schema/dashboard identificam essa conta.
    'conta3':    {'nome': 'Petclean BR', 'pasta': 'petclean/raw'},
    'ozitp':     {'nome': 'OZITP',     'pasta': 'ozitp/raw'},
    'jolitex':   {'nome': 'Jolitex',   'pasta': 'jolitex/raw'},
    'balboa':    {'nome': 'Balboa',    'pasta': 'balboa/raw'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'pasta': 'plastpet/raw'},
    'wiwu':      {'nome': 'WIWU', 'pasta': 'wiwu/raw'},
    'petiko':    {'nome': 'PETIKO', 'pasta': 'petiko/raw'},
}

SAIDA = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_vendor.json'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def amount(v):
    """Extrai .amount de campos monetários {"amount":X,"currencyCode":"BRL"}."""
    if isinstance(v, dict):
        return v.get('amount', 0) or 0
    return v or 0


def n(v, padrao=0):
    return padrao if v is None else v


def dinheiro(v):
    """Valor monetário da VendorOrders API ({"amount": "401.77", ...}, amount
    vem como STRING) -> float."""
    try:
        return float(amount(v))
    except (TypeError, ValueError):
        return 0.0


def parse_iso(s):
    """ISO 8601 da API ('2026-09-10T06:07:29.395Z') -> datetime com fuso UTC.
    Retorna None se vazio ou inválido."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def enxuto(x):
    """10.0 -> 10 (JSON menor); mantém decimais quando existem."""
    x = round(float(x), 2)
    return int(x) if x.is_integer() else x


# ---------------------------------------------------------------------------
# Qualidade de listings (Listings Items API) — status, erros e avisos reais
# ---------------------------------------------------------------------------

def carregar_qualidade_listings(pasta_raw):
    """Lê qualidade_listings.json (gerado por capturar_qualidade_listings.py)
    e estrutura em: por ASIN (status, suprimido, erros, avisos) + resumo da
    conta (contagens). Se o arquivo não existir, retorna bloco vazio."""
    arq = f'{pasta_raw}/qualidade_listings.json'
    bruto = {}
    if os.path.exists(arq):
        try:
            bruto = json.load(open(arq, encoding='utf-8'))
        except Exception:
            bruto = {}

    asins = {}
    suprimidos = []
    for asin, info in bruto.items():
        issues = info.get('issues') or []
        erros = [i for i in issues if i.get('severity') == 'ERROR']
        avisos = [i for i in issues if i.get('severity') == 'WARNING']
        suprimido = any(
            (a.get('action') == 'LISTING_SUPPRESSED')
            for i in erros
            for a in ((i.get('enforcements') or {}).get('actions') or [])
        )
        asins[asin] = {
            'sku': info.get('sku'),
            'status': info.get('status') or [],
            'suprimido': suprimido,
            'qtdErros': len(erros),
            'qtdAvisos': len(avisos),
            'erros': [{'codigo': i.get('code'), 'mensagem': i.get('message')} for i in erros],
            'avisos': [{'codigo': i.get('code'), 'mensagem': i.get('message'),
                        'atributos': i.get('attributeNames')} for i in avisos],
        }
        if suprimido:
            suprimidos.append(asin)

    total = len(asins)
    saudaveis = sum(1 for a in asins.values() if a['qtdErros'] == 0 and a['qtdAvisos'] == 0)
    resumo = {
        'totalAsins': total,
        'suprimidos': len(suprimidos),
        'comErro': sum(1 for a in asins.values() if a['qtdErros'] > 0),
        'comAviso': sum(1 for a in asins.values() if a['qtdAvisos'] > 0),
        'saudaveis': saudaveis,
        'pctSaudaveis': round(100 * saudaveis / total, 1) if total else 0,
    }
    return {'asins': asins, 'resumo': resumo, 'listaSuprimidos': sorted(suprimidos)}


# ---------------------------------------------------------------------------
# Sell-in — pedidos de compra (VendorOrders API)
# ---------------------------------------------------------------------------

_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _dedupe_por_po(arquivos, data_do_po):
    """Lê listas de POs de vários arquivos e mantém UMA versão por
    purchaseOrderNumber: a de data de atualização mais recente
    (data_do_po(po)); empate -> a do arquivo modificado por último.

    Sempre necessário, não é workaround: o mesmo PO pode estar em mais de um
    arquivo, e o status de um PO muda depois que a semana dele foi baixada.

    Retorna (dict po_num -> po, n_duplicatas, lista_de_arquivos_ignorados)."""
    melhores, dup, ignorados = {}, 0, []
    for arq in arquivos:
        try:
            with open(arq, encoding='utf-8') as f:
                dados = json.load(f)
        except Exception as e:
            ignorados.append(f'{os.path.basename(arq)} (erro ao ler: {e})')
            continue
        if not isinstance(dados, list):
            # ex.: cache antigo que salvou {"erro": ...} em vez da lista
            ignorados.append(f'{os.path.basename(arq)} (conteúdo não é lista de POs)')
            continue
        mtime = os.path.getmtime(arq)
        for po in dados:
            num = po.get('purchaseOrderNumber')
            if not num:
                continue
            chave = (parse_iso(data_do_po(po)) or _DT_MIN, mtime)
            if num in melhores:
                dup += 1
                if chave <= melhores[num][0]:
                    continue
            melhores[num] = (chave, po)
    return {k: v[1] for k, v in melhores.items()}, dup, ignorados


def processar_pedidos(pasta_raw, agora=None):
    """Gera os blocos de sell-in do CONTAS a partir de
      status_pedidos_*.json (get_purchase_orders_status: aceito/rejeitado/recebido)
      pedidos_*.json        (get_purchase_orders: só para deliveryWindow)

    Retorna (blocos, avisos). `agora` = referência para calcular atraso
    (padrão: momento da execução, UTC)."""
    agora = agora or datetime.now(timezone.utc)
    avisos = []
    blocos = {
        'sellin': {}, 'sellinMes': {}, 'sellinRecebidoMes': {}, 'atrasados': {},
        'repetidos': {}, 'naoAtendidos': {}, 'markupMes': {}, 'markupGeral': 0,
        'totalPOs': 0, 'sellinInfo': {}, 'pedidos': [],
    }

    arqs_status = sorted(glob.glob(f'{pasta_raw}/status_pedidos_*.json'))
    arqs_pedidos = sorted(glob.glob(f'{pasta_raw}/pedidos_*.json'))
    if os.path.exists(f'{pasta_raw}/purchase_orders_60dias.json'):
        avisos.append('purchase_orders_60dias.json (formato antigo) encontrado e IGNORADO — '
                      'o sell-in agora vem só de status_pedidos_*.json')
    if not arqs_status:
        avisos.append('nenhum status_pedidos_*.json — blocos de sell-in ficam vazios '
                      '(rode capturar_pedidos.py)')
        return blocos, avisos

    status, dup_s, ign_s = _dedupe_por_po(arqs_status, lambda po: po.get('lastUpdatedDate'))
    pedidos, dup_p, ign_p = _dedupe_por_po(
        arqs_pedidos, lambda po: (po.get('orderDetails') or {}).get('purchaseOrderStateChangedDate'))
    for x in ign_s + ign_p:
        avisos.append(f'arquivo ignorado: {x}')

    # janela de entrega, por PO (só existe em pedidos_*.json)
    janela_fim, janela_txt = {}, {}
    for num, po in pedidos.items():
        dw = (po.get('orderDetails') or {}).get('deliveryWindow') or ''
        if '--' in dw:
            ini_s, fim_s = dw.split('--', 1)
            janela_txt[num] = (ini_s, fim_s)
            fim = parse_iso(fim_s)
            if fim:
                janela_fim[num] = fim

    cont = defaultdict(int)  # contadores de qualidade do dado, só para avisos

    def unidades(q):
        """{"amount":N,"unitOfMeasure":"Eaches"|"Cases","unitSize":K} -> unidades."""
        if not isinstance(q, dict):
            return 0.0
        try:
            a = float(q.get('amount') or 0)
        except (TypeError, ValueError):
            return 0.0
        if str(q.get('unitOfMeasure', 'Eaches')).lower().startswith('case'):
            cont['caixas'] += 1
            a *= float(q.get('unitSize') or 1)
        return a

    campos = ('pedido', 'cancelado', 'conf', 'confValido', 'rej', 'recebido', 'custo', 'custoRecebido', 'pendente')
    novo_acc = lambda: dict({c: 0.0 for c in campos}, pos=set())
    acc_asin = defaultdict(novo_acc)
    acc_mes = defaultdict(novo_acc)
    acc_receb = defaultdict(lambda: {'recebido': 0.0, 'custoRecebido': 0.0, 'pos': set()})
    acc_atraso = defaultdict(lambda: {'un': 0.0, 'custo': 0.0, 'pos': set(), 'maxDias': 0})
    nao_atendidos = defaultdict(float)
    mk_mes, mk_all = defaultdict(list), []
    po_asin = defaultdict(set)
    ultima_atualizacao = None
    lista_pedidos = []  # bloco `pedidos`: um registro por PO, com os itens

    for num, po in status.items():
        dmes = (po.get('purchaseOrderDate') or '')[:7]
        aberto = po.get('purchaseOrderStatus') == 'OPEN'
        fim_janela = janela_fim.get(num)
        atu = parse_iso(po.get('lastUpdatedDate'))
        if atu and (ultima_atualizacao is None or atu > ultima_atualizacao):
            ultima_atualizacao = atu
        od = (pedidos.get(num) or {}).get('orderDetails') or {}
        reg = {
            'po': num, 'data': po.get('purchaseOrderDate'), 'status': po.get('purchaseOrderStatus'),
            'estado': (pedidos.get(num) or {}).get('purchaseOrderState'), 'tipo': od.get('purchaseOrderType'),
            'janelaIni': janela_txt.get(num, (None, None))[0], 'janelaFim': janela_txt.get(num, (None, None))[1],
            'atualizado': po.get('lastUpdatedDate'), 'destino': (po.get('shipToParty') or {}).get('partyId'),
            'atrasado': False, 'diasAtraso': 0, 'itens': [],
        }
        lista_pedidos.append(reg)

        for it in po.get('itemStatus') or []:
            a = it.get('buyerProductIdentifier')
            if not a:
                continue
            po_asin[a].add(num)
            cu = dinheiro(it.get('netCost'))
            lp = dinheiro(it.get('listPrice'))

            # --- pedido / cancelado ---
            # Confirmado com dado real (22/09/2026): orderedQuantity do nível de cima
            # é o pedido ATUAL, já líquido de cancelamento (ex.: pediu 120, cancelou 3
            # -> 117; PO cancelado inteiro -> 0). O pedido ORIGINAL é o primeiro
            # registro de orderedQuantityDetails[]. Cancelado = original - atual.
            oq = it.get('orderedQuantity') or {}
            atual = unidades(oq.get('orderedQuantity'))
            hist = sorted(oq.get('orderedQuantityDetails') or [], key=lambda d: d.get('updatedDate') or '')
            ped = max(unidades(hist[0].get('orderedQuantity')) if hist else atual, atual)
            canc = ped - atual

            # --- aceito / rejeitado: vem de acknowledgementStatusDetails[] ---
            # (rejectedQuantity NÃO vem no nível de cima; era por isso que `rej` dava 0)
            ack = it.get('acknowledgementStatus') or {}
            det = ack.get('acknowledgementStatusDetails') or []
            # Confirmado com dado real (22/09/2026): os registros de
            # acknowledgementStatusDetails[] são a fonte certa. O acceptedQuantity do
            # nível de cima às vezes vem inconsistente (ex.: PARTIALLY_ACCEPTED com
            # aceito 23 para um item de 12 pedidos e 12 aceitos no registro), então
            # ele só é usado quando não há registros.
            if det:
                ac = sum(unidades(x.get('acceptedQuantity')) for x in det)
                rj = sum(unidades(x.get('rejectedQuantity')) for x in det)
                topo_ac = ack.get('acceptedQuantity')
                if topo_ac is not None and abs(unidades(topo_ac) - ac) > 1e-9:
                    cont['ack_topo_divergente'] += 1
            else:
                ac = unidades(ack.get('acceptedQuantity'))
                rj = unidades(ack.get('rejectedQuantity'))

            if ac + rj > ped + 1e-9:
                cont['excesso'] += 1  # aceito + rejeitado > pedido original: não deveria acontecer

            # --- recebido ---
            rs = it.get('receivingStatus') or {}
            rec = unidades(rs.get('receivedQuantity'))

            # aceito que continua valendo: a Amazon pode cancelar DEPOIS do aceite,
            # então vale no máximo o pedido atual. Mas o que já foi recebido não foi
            # cancelado (dado real: pedido atual 1 após cancelar 11, recebido 12),
            # então o recebido também conta, sempre limitado ao aceito.
            valido = min(ac, max(atual, rec))
            falta = max(0.0, valido - rec)
            pend = falta if aberto else 0.0  # PO fechado com falta não está "pendente": não vai chegar mais

            for x, chave_po in ((acc_asin[a], num), (acc_mes[dmes], num)):
                x['pedido'] += ped; x['cancelado'] += canc
                x['conf'] += ac; x['confValido'] += valido; x['rej'] += rj; x['recebido'] += rec
                x['custo'] += valido * cu; x['custoRecebido'] += rec * cu
                x['pendente'] += pend
                x['pos'].add(chave_po)

            # recebido agrupado pelo mês do ÚLTIMO recebimento do item; sem
            # lastReceiveDate, usa a última atualização do PO (aviso no log)
            if rec > 0:
                lrd = rs.get('lastReceiveDate')
                if not lrd:
                    lrd = po.get('lastUpdatedDate')
                    cont['recebido_sem_data'] += 1
                if lrd:
                    y = acc_receb[lrd[:7]]
                    y['recebido'] += rec; y['custoRecebido'] += rec * cu; y['pos'].add(num)

            # atrasado: PO aberto, janela de entrega já venceu, aceito > recebido
            atrasado_item = False
            if aberto and falta > 0:
                if fim_janela is None:
                    cont['sem_janela'] += 1
                elif fim_janela < agora:
                    atrasado_item = True
                    dias = (agora - fim_janela).days
                    z = acc_atraso[a]
                    z['un'] += falta; z['custo'] += falta * cu; z['pos'].add(num)
                    z['maxDias'] = max(z['maxDias'], dias)
                    reg['atrasado'] = True
                    reg['diasAtraso'] = max(reg['diasAtraso'], dias)

            reg['itens'].append({
                'seq': it.get('itemSequenceNumber'), 'asin': a, 'ean': it.get('vendorProductIdentifier'),
                'pedido': enxuto(ped), 'cancelado': enxuto(canc), 'conf': enxuto(ac), 'confValido': enxuto(valido), 'rej': enxuto(rj),
                'recebido': enxuto(rec), 'pendente': enxuto(pend), 'atrasado': atrasado_item,
                'statusConf': ack.get('confirmationStatus'), 'statusRec': rs.get('receiveStatus'),
                'dataReceb': rs.get('lastReceiveDate'), 'custoUn': round(cu, 2), 'precoLista': round(lp, 2),
            })

            if rj > 0:
                nao_atendidos[a] += rj
            if cu > 0:
                mk_mes[dmes].append((lp - cu) / cu)
                mk_all.append((lp - cu) / cu)

    def fechar(v):
        out = {c: enxuto(v[c]) for c in campos}
        out['pos'] = len(v['pos'])
        return out

    blocos['sellin'] = {a: fechar(v) for a, v in acc_asin.items()}
    blocos['sellinMes'] = {m: fechar(v) for m, v in sorted(acc_mes.items()) if m}
    blocos['sellinRecebidoMes'] = {m: {'recebido': enxuto(v['recebido']), 'custoRecebido': enxuto(v['custoRecebido']),
                                       'pos': len(v['pos'])} for m, v in sorted(acc_receb.items())}
    blocos['atrasados'] = {a: {'un': enxuto(v['un']), 'custo': enxuto(v['custo']), 'pos': len(v['pos']),
                               'maxDias': v['maxDias']} for a, v in acc_atraso.items()}
    blocos['repetidos'] = {a: len(p) for a, p in po_asin.items() if len(p) > 1}
    blocos['naoAtendidos'] = {a: enxuto(v) for a, v in nao_atendidos.items()}
    blocos['markupMes'] = {m: (sum(v) / len(v) if v else 0) for m, v in sorted(mk_mes.items()) if m}
    blocos['markupGeral'] = sum(mk_all) / len(mk_all) if mk_all else 0
    blocos['totalPOs'] = len(status)

    # POs que só existem em pedidos_*.json (sem status capturado): entram na lista
    # com o que se sabe do pedido, marcados como SEM_STATUS
    for num in set(pedidos) - set(status):
        po = pedidos[num]; od = po.get('orderDetails') or {}
        ini_s, fim_s = janela_txt.get(num, (None, None))
        lista_pedidos.append({
            'po': num, 'data': od.get('purchaseOrderDate'), 'status': 'SEM_STATUS',
            'estado': po.get('purchaseOrderState'), 'tipo': od.get('purchaseOrderType'),
            'janelaIni': ini_s, 'janelaFim': fim_s, 'atualizado': od.get('purchaseOrderStateChangedDate'),
            'destino': (od.get('shipToParty') or {}).get('partyId'), 'atrasado': False, 'diasAtraso': 0,
            'itens': [{
                'seq': it.get('itemSequenceNumber'), 'asin': it.get('amazonProductIdentifier'),
                'ean': it.get('vendorProductIdentifier'), 'pedido': enxuto(unidades(it.get('orderedQuantity'))),
                'cancelado': None, 'conf': None, 'confValido': None, 'rej': None, 'recebido': None, 'pendente': None, 'atrasado': False,
                'statusConf': None, 'statusRec': None, 'dataReceb': None,
                'custoUn': round(dinheiro(it.get('netCost')), 2), 'precoLista': round(dinheiro(it.get('listPrice')), 2),
            } for it in (od.get('items') or [])],
        })

    # totais por PO (custo = confirmado ainda válido x custo unitário, como em sellin)
    for reg in lista_pedidos:
        its = reg['itens']
        soma = lambda campo: enxuto(sum((i[campo] or 0) for i in its))
        reg['tot'] = {
            'itens': len(its), 'pedido': soma('pedido'), 'cancelado': soma('cancelado'), 'conf': soma('conf'),
            'confValido': soma('confValido'), 'rej': soma('rej'),
            'recebido': soma('recebido'), 'pendente': soma('pendente'),
            'custoPedido': enxuto(sum((i['pedido'] or 0) * i['custoUn'] for i in its)),
            'custo': enxuto(sum((i['confValido'] or 0) * i['custoUn'] for i in its)),
            'custoRecebido': enxuto(sum((i['recebido'] or 0) * i['custoUn'] for i in its)),
        }
    lista_pedidos.sort(key=lambda r: r['data'] or '', reverse=True)
    blocos['pedidos'] = lista_pedidos
    blocos['sellinInfo'] = {
        'referencia': agora.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'statusAtualizadoAte': ultima_atualizacao.strftime('%Y-%m-%dT%H:%M:%SZ') if ultima_atualizacao else None,
        'arquivosStatus': len(arqs_status), 'arquivosPedidos': len(arqs_pedidos),
    }

    # --- avisos de qualidade do dado ---
    if dup_s:
        avisos.append(f'{dup_s} ocorrência(s) repetida(s) de PO entre arquivos de status (dedupe aplicado)')
    so_em_pedidos = set(pedidos) - set(status)
    if so_em_pedidos:
        avisos.append(f'{len(so_em_pedidos)} PO(s) em pedidos_*.json sem status correspondente — '
                      f'fora do sell-in (bloco semanal de status faltando ou com erro?)')
    if cont['sem_janela']:
        avisos.append(f"{cont['sem_janela']} item(ns) aberto(s) sem deliveryWindow (PO ausente de pedidos_*.json) — "
                      f"não avaliados para atraso")
    if cont['recebido_sem_data']:
        avisos.append(f"{cont['recebido_sem_data']} item(ns) com quantidade recebida mas sem lastReceiveDate — "
                      f"em sellinRecebidoMes pelo mês da última atualização do PO")
    if cont['excesso']:
        avisos.append(f"{cont['excesso']} item(ns) com aceito + rejeitado MAIOR que o pedido original — "
                      f"não deveria acontecer; mandar um exemplo para análise")
    if cont['ack_topo_divergente']:
        avisos.append(f"{cont['ack_topo_divergente']} item(ns) com acceptedQuantity do nível de cima diferente da soma "
                      f"dos registros de confirmação — usada a soma dos registros (comportamento conhecido da API)")
    if cont['caixas']:
        avisos.append(f"{cont['caixas']} quantidade(s) em caixas (Cases) convertida(s) para unidades via unitSize — "
                      f"conferir se netCost é por unidade nesses itens")
    return blocos, avisos


# ---------------------------------------------------------------------------
# Etapa 1 — transforma os relatórios raw de UMA conta no bloco CONTAS[conta]
# ---------------------------------------------------------------------------

def processar_conta(pasta_raw):
    vendas, estoque, trafego, margem = (defaultdict(dict), defaultdict(dict),
                                         defaultdict(dict), defaultdict(dict))
    agg_vendas, agg_estoque, agg_trafego, agg_margem = {}, {}, {}, {}

    # --- Vendas ---
    for arq in sorted(glob.glob(f'{pasta_raw}/vendas_mes_*.json')):
        d = json.load(open(arq))
        for r in d.get('salesByAsin', []):
            mes = r['startDate'][:7]
            vendas[r['asin']][mes] = {
                'orderedRevenue': amount(r.get('orderedRevenue')), 'orderedUnits': n(r.get('orderedUnits')),
                'shippedRevenue': amount(r.get('shippedRevenue')), 'shippedUnits': n(r.get('shippedUnits')),
                'customerReturns': n(r.get('customerReturns')), 'shippedCogs': amount(r.get('shippedCogs')),
            }
        for r in d.get('salesAggregate', []):
            mes = r['startDate'][:7]
            agg_vendas[mes] = {
                'orderedRevenue': amount(r.get('orderedRevenue')), 'orderedUnits': n(r.get('orderedUnits')),
                'shippedRevenue': amount(r.get('shippedRevenue')), 'shippedUnits': n(r.get('shippedUnits')),
                'customerReturns': n(r.get('customerReturns')), 'shippedCogs': amount(r.get('shippedCogs')),
            }

    # --- Estoque ---
    for arq in sorted(glob.glob(f'{pasta_raw}/estoque_mes_*.json')):
        d = json.load(open(arq))
        for r in d.get('inventoryByAsin', []):
            mes = r['startDate'][:7]
            estoque[r['asin']][mes] = {
                'sellableUnits': n(r.get('sellableOnHandInventoryUnits')),
                'sellableCost': amount(r.get('sellableOnHandInventoryCost')),
                'aged90Units': n(r.get('aged90PlusDaysSellableInventoryUnits')),
                'unhealthyUnits': n(r.get('unhealthyInventoryUnits')),
                'unhealthyCost': amount(r.get('unhealthyInventoryCost')),
                'openPO': n(r.get('openPurchaseOrderUnits')), 'sellThrough': n(r.get('sellThroughRate')),
                'oosRate': n(r.get('procurableProductOutOfStockRate')),
                'receiveFillRate': n(r.get('receiveFillRate')),
                'leadTime': n(r.get('averageVendorLeadTimeDays')),
                'unfilledUnits': n(r.get('unfilledCustomerOrderedUnits')),
                'temInfo': r.get('sellableOnHandInventoryUnits') is not None,
            }
        for r in d.get('inventoryAggregate', []):
            mes = r['startDate'][:7]
            agg_estoque[mes] = {
                'sellableUnits': n(r.get('sellableOnHandInventoryUnits')),
                'sellableCost': amount(r.get('sellableOnHandInventoryCost')),
                'unhealthyCost': amount(r.get('unhealthyInventoryCost')),
                'unhealthyUnits': n(r.get('unhealthyInventoryUnits')),
                'oosRate': n(r.get('procurableProductOutOfStockRate')),
                'receiveFillRate': n(r.get('receiveFillRate')),
                'leadTime': n(r.get('averageVendorLeadTimeDays')),
                'openPO': n(r.get('openPurchaseOrderUnits')), 'sellThrough': n(r.get('sellThroughRate')),
            }

    # --- Tráfego ---
    for arq in sorted(glob.glob(f'{pasta_raw}/trafego_mes_*.json')):
        d = json.load(open(arq))
        for r in d.get('trafficByAsin', []):
            mes = r['startDate'][:7]
            trafego[r['asin']][mes] = {'glanceViews': n(r.get('glanceViews'))}
        for r in d.get('trafficAggregate', []):
            mes = r['startDate'][:7]
            agg_trafego[mes] = {'glanceViews': n(r.get('glanceViews'))}

    # --- Margem ---
    for arq in sorted(glob.glob(f'{pasta_raw}/margem_mes_*.json')):
        d = json.load(open(arq))
        for r in d.get('netPureProductMarginByAsin', []):
            mes = r['startDate'][:7]
            margem[r['asin']][mes] = {'npm': r.get('netPureProductMargin')}
        for r in d.get('netPureProductMarginAggregate', []):
            mes = r['startDate'][:7]
            agg_margem[mes] = {'npm': r.get('netPureProductMargin')}

    # --- Sell-in (pedidos de compra) → ver processar_pedidos() ---
    si, avisos_si = processar_pedidos(pasta_raw)
    sellin = si['sellin']

    # --- custoMedio (ponderado por volume enviado) ---
    custo_medio = {}
    for a, ms in vendas.items():
        tc = sum(v['shippedCogs'] for v in ms.values())
        tu = sum(v['shippedUnits'] for v in ms.values())
        if tu > 0:
            custo_medio[a] = tc / tu

    # --- Previsão (forecast) ---
    prev_arq = f'{pasta_raw}/previsao_60dias.json'
    previsao, previsao_mes = {}, {}
    if os.path.exists(prev_arq):
        d = json.load(open(prev_arq))
        pa = d.get('forecastByAsin', [])
        if pa:
            g = datetime.strptime(pa[0]['forecastGenerationDate'], '%Y-%m-%d')
            lim = g + timedelta(days=60)
            pacc = defaultdict(lambda: {'mean': 0.0, 'p70': 0.0, 'p80': 0.0, 'p90': 0.0})
            pmes = defaultdict(lambda: {'mean': 0.0, 'p70': 0.0, 'p80': 0.0, 'p90': 0.0, 'valor': 0.0})
            for r in pa:
                if datetime.strptime(r['startDate'], '%Y-%m-%d') > lim:
                    continue
                a = r['asin']
                mu = n(r.get('meanForecastUnits'))
                x = pacc[a]
                x['mean'] += mu; x['p70'] += n(r.get('p70ForecastUnits'))
                x['p80'] += n(r.get('p80ForecastUnits')); x['p90'] += n(r.get('p90ForecastUnits'))
                y = pmes[r['startDate'][:7]]
                y['mean'] += mu; y['p70'] += n(r.get('p70ForecastUnits'))
                y['p80'] += n(r.get('p80ForecastUnits')); y['p90'] += n(r.get('p90ForecastUnits'))
                if a in custo_medio:
                    y['valor'] += mu * custo_medio[a]
            previsao = dict(pacc)
            previsao_mes = dict(pmes)

    # --- Curva ABC ---
    tot_rec = {}
    for a, ms in vendas.items():
        r = sum(v['orderedRevenue'] for v in ms.values())
        if r > 0:
            tot_rec[a] = r
    ordenado = sorted(tot_rec.items(), key=lambda x: -x[1])
    soma = sum(v for _, v in ordenado) or 1
    abc = {}
    ac = 0
    for a, v in ordenado:
        ac += v
        p = ac / soma
        abc[a] = {'valor': v, 'classe': 'A' if p <= .8 else ('B' if p <= .95 else 'C'), 'pct': v / soma}

    # --- ticket / markupVarejo por mês ---
    ticket_markup = {}
    for m, ag in agg_vendas.items():
        ticket_markup[m] = {
            'ticket': ag['shippedRevenue'] / ag['shippedUnits'] if ag['shippedUnits'] > 0 else 0,
            'markupVarejo': (ag['shippedRevenue'] - ag['shippedCogs']) / ag['shippedCogs'] if ag['shippedCogs'] > 0 else 0,
        }

    todos_asins = set(vendas) | set(estoque)
    nunca = sorted(todos_asins - set(sellin))

    # --- catalogo (nome do produto, imagem, BSR) -- carregado de catalogo.json,
    # gerado separadamente pelo capturar_catalogo.py. Se o arquivo nao existir
    # ainda (captura nao rodada), fica vazio e o dashboard cai no fallback (so ASIN).
    catalogo_arq = f'{pasta_raw}/catalogo.json'
    catalogo = {}
    if os.path.exists(catalogo_arq):
        try:
            catalogo = json.load(open(catalogo_arq, encoding='utf-8'))
        except Exception:
            catalogo = {}

    # --- qualidade (aproximação própria do CDQ) -- carregado de
    # qualidade_catalogo.json, gerado pelo calcular_qualidade_catalogo.py a
    # partir de 5 capturas (listings_issues, listings_attributes,
    # imagens_completas, relationships, aplus_content_massa). Formato:
    # {"asins": {"<asin>": {...score_geral, grau_geral, componentes...}},
    #  "nao_pertence_a_conta": [...]}
    # Se o arquivo nao existir ainda, fica vazio e o dashboard nao mostra a
    # aba de qualidade pra essa conta (ou mostra "sem dados").
    qualidade_arq = f'{pasta_raw}/qualidade_catalogo.json'
    qualidade = {'asins': {}, 'nao_pertence_a_conta': []}
    if os.path.exists(qualidade_arq):
        try:
            qualidade = json.load(open(qualidade_arq, encoding='utf-8'))
        except Exception:
            qualidade = {'asins': {}, 'nao_pertence_a_conta': []}

    # --- qualidadeListings (dado real da Amazon: status, suprimido, erros e
    # avisos por ASIN) -- carregado de qualidade_listings.json, gerado por
    # capturar_qualidade_listings.py via Listings Items API. Ver função
    # carregar_qualidade_listings() acima. Independente do bloco `qualidade`.
    qualidade_listings = carregar_qualidade_listings(pasta_raw)

    return {
        'vendas': dict(vendas), 'estoque': dict(estoque), 'trafego': dict(trafego), 'margem': dict(margem),
        'aggVendas': agg_vendas, 'aggEstoque': agg_estoque, 'aggTrafego': agg_trafego, 'aggMargem': agg_margem,
        'sellin': sellin, 'sellinMes': si['sellinMes'], 'sellinRecebidoMes': si['sellinRecebidoMes'],
        'atrasados': si['atrasados'], 'sellinInfo': si['sellinInfo'], 'pedidos': si['pedidos'],
        'repetidos': si['repetidos'], 'naoAtendidos': si['naoAtendidos'],
        'nuncaComprados': nunca, 'abc': abc, 'ticketMarkup': ticket_markup, 'markupMes': si['markupMes'],
        'markupGeral': si['markupGeral'], 'totalPOs': si['totalPOs'], 'previsao': previsao, 'previsaoMes': previsao_mes,
        'custoMedio': custo_medio, 'catalogo': catalogo, 'qualidade': qualidade,
        'qualidadeListings': qualidade_listings,
        '_avisos_sellin': avisos_si,  # removido em main() antes de salvar
    }


# ---------------------------------------------------------------------------
# Etapa 2 — gera o bloco `analise` (diagnósticos automáticos) para UMA conta
# ---------------------------------------------------------------------------

def analisar(d):
    V, E, T, M = d['vendas'], d['estoque'], d['trafego'], d['margem']
    AV, AE, AT, AM = d['aggVendas'], d['aggEstoque'], d['aggTrafego'], d['aggMargem']
    meses = sorted(set(list(AV) + list(AE) + list(AT) + list(AM)))
    ult = next((m for m in reversed(meses) if AV.get(m, {}).get('orderedUnits', 0) > 0), None)
    if not ult:
        return None

    tv = sum(AT.get(m, {}).get('glanceViews', 0) for m in meses)
    tu = sum(AV.get(m, {}).get('orderedUnits', 0) for m in meses)
    conv_geral = tu / tv if tv > 0 else 0
    ticket = d['ticketMarkup'].get(ult, {}).get('ticket', 0)
    npm = AM.get(ult, {}).get('npm')

    perfil = {}
    for a in set(V) | set(E) | set(T) | set(M):
        v = V.get(a, {}).get(ult, {}); e = E.get(a, {}).get(ult, {})
        t = T.get(a, {}).get(ult, {}); mg = M.get(a, {}).get(ult, {}); s = d['sellin'].get(a, {})
        views = t.get('glanceViews', 0); ped = v.get('orderedUnits', 0)
        perfil[a] = {
            'views': views, 'ped': ped, 'env': v.get('shippedUnits', 0), 'rec': v.get('orderedRevenue', 0),
            'cogs': v.get('shippedCogs', 0), 'dev': v.get('customerReturns', 0),
            'est': e.get('sellableUnits', 0), 'parado': e.get('unhealthyUnits', 0),
            'a90': e.get('aged90Units', 0), 'giro': e.get('sellThrough', 0), 'openPO': e.get('openPO', 0),
            'temInfoEst': e.get('temInfo', False),
            'conv': (ped / views) if views > 0 else None, 'npm': mg.get('npm'),
            'siConf': s.get('conf', 0), 'siCusto': s.get('custo', 0),
        }

    views_list = sorted([p['views'] for p in perfil.values() if p['views'] > 0])
    v_med = views_list[len(views_list) // 2] if views_list else 0

    diags = []

    # 1 — ruptura com demanda (chamado "perdidos" no schema)
    perdidos = [{'asin': a, 'views': p['views'], 'un': p['views'] * conv_geral, 'rs': p['views'] * conv_geral * ticket}
                for a, p in perfil.items() if p['views'] > 0 and p['temInfoEst'] and p['est'] == 0 and p['ped'] == 0]
    perdidos.sort(key=lambda x: -x['rs'])
    if perdidos:
        diags.append({'tipo': 'perdidos', 'titulo': 'Ruptura em produtos com procura',
            'impacto': sum(x['rs'] for x in perdidos), 'qtd': len(perdidos),
            'explica': 'Produtos que tiveram visitas na página mas estavam sem estoque. A estimativa usa a taxa de conversão média da conta aplicada às visitas perdidas.',
            'acao': 'Cobrar reposição junto ao comprador da Amazon e revisar o ponto de pedido destes itens.',
            'itens': perdidos[:12]})

    # 2 — alto tráfego, baixa conversão
    baixa = [{'asin': a, 'views': p['views'], 'conv': p['conv'], 'ped': p['ped'], 'est': p['est'],
              'rs': (conv_geral - p['conv']) * p['views'] * ticket}
             for a, p in perfil.items()
             if p['views'] >= max(v_med, 10) and p['conv'] is not None and p['conv'] < conv_geral * 0.5]
    baixa.sort(key=lambda x: -x['rs'])
    if baixa:
        diags.append({'tipo': 'conversao', 'titulo': 'Tráfego alto convertendo mal',
            'impacto': sum(x['rs'] for x in baixa), 'qtd': len(baixa),
            'explica': 'Produtos bem acima da mediana de visitas, mas com conversão menor que metade da média da conta. O valor é quanto renderiam se convertessem na média.',
            'acao': 'Revisar preço, imagens, título, bullets e avaliações. O cliente chega mas não compra.',
            'itens': baixa[:12]})

    # 3 — capital parado
    parado = [{'asin': a, 'parado': p['parado'], 'est': p['est'], 'a90': p['a90'], 'giro': p['giro']}
              for a, p in perfil.items() if p['parado'] > 0]
    parado.sort(key=lambda x: -x['parado'])
    total_parado_rs = AE.get(ult, {}).get('unhealthyCost', 0)
    if parado:
        diags.append({'tipo': 'parado', 'titulo': 'Capital imobilizado em estoque parado',
            'impacto': total_parado_rs, 'qtd': len(parado),
            'explica': 'Estoque classificado pela Amazon como excedente frente à demanda prevista. É dinheiro que já saiu do seu caixa e não está girando.',
            'acao': 'Negociar promoção, ação de liquidação ou reduzir o próximo pedido destes itens.',
            'itens': parado[:12]})

    # 4 — vazamento de margem
    vaz = []
    if npm:
        vaz = [{'asin': a, 'npm': p['npm'], 'rec': p['rec'], 'rs': p['rec'] * (npm - p['npm'])}
               for a, p in perfil.items() if p['npm'] is not None and p['rec'] > 0 and p['npm'] < npm * 0.7]
        vaz.sort(key=lambda x: -x['rs'])
    if vaz:
        diags.append({'tipo': 'margem', 'titulo': 'Produtos puxando a margem para baixo',
            'impacto': sum(x['rs'] for x in vaz), 'qtd': len(vaz),
            'explica': f'Produtos com margem líquida abaixo de 70% da média da conta ({npm*100:.1f}%). O valor é quanto a mais renderiam na margem média.',
            'acao': 'Renegociar custo com a Amazon ou revisar o preço de tabela destes itens.',
            'itens': vaz[:12]})

    # 5 — oportunidade de visibilidade
    op = [{'asin': a, 'views': p['views'], 'conv': p['conv'], 'rec': p['rec'],
           'rs': (v_med - p['views']) * p['conv'] * ticket}
          for a, p in perfil.items()
          if p['conv'] is not None and p['conv'] > conv_geral * 1.5 and 0 < p['views'] < v_med]
    op.sort(key=lambda x: -x['rs'])
    if op:
        diags.append({'tipo': 'oportunidade', 'titulo': 'Produtos que convertem bem mas pouca gente vê',
            'impacto': sum(x['rs'] for x in op), 'qtd': len(op),
            'explica': 'Conversão acima de 1,5x a média com visitas abaixo da mediana. O valor estima o ganho se atingissem a visibilidade mediana.',
            'acao': 'Investir em mídia, cupom ou melhorar posicionamento de busca. Aqui o produto já provou que vende.',
            'itens': op[:12]})

    diags.sort(key=lambda x: -x['impacto'])

    receitas = sorted([p['rec'] for p in perfil.values() if p['rec'] > 0], reverse=True)
    tot = sum(receitas) or 1

    serie_gap = {m: {'si': d['sellinMes'].get(m, {}).get('custo'), 'so': AV.get(m, {}).get('shippedCogs')} for m in meses}
    cobertura = {}
    for m in meses:
        av = AV.get(m, {}); ae = AE.get(m, {})
        vd = av.get('shippedUnits', 0) / 30 if av.get('shippedUnits', 0) > 0 else 0
        cobertura[m] = ae.get('sellableUnits', 0) / vd if vd > 0 else None
    conversao = {m: (AV.get(m, {}).get('orderedUnits', 0) / AT[m]['glanceViews']
                      if AT.get(m, {}).get('glanceViews', 0) > 0 else None) for m in meses}

    scatter = [{'a': a, 'x': p['views'], 'y': round((p['conv'] or 0) * 100, 2), 'r': round(p['rec'], 2)}
               for a, p in perfil.items() if p['views'] > 0]

    top = sorted([(a, p['rec']) for a, p in perfil.items() if p['rec'] > 0], key=lambda x: -x[1])[:12]

    return {
        'ultimoMes': ult, 'convGeral': conv_geral, 'ticket': ticket, 'npm': npm, 'viewsMediana': v_med,
        'diagnosticos': diags, 'perfil': perfil,
        'concentracao': {'top5': sum(receitas[:5]) / tot, 'nAsins': len(receitas)},
        'serieGap': serie_gap, 'cobertura': cobertura, 'conversao': conversao,
        'scatter': scatter, 'topAsins': [{'a': a, 'v': v} for a, v in top],
    }


# ---------------------------------------------------------------------------
# Etapa 3 — roda para todas as contas e salva dados_vendor.json
# ---------------------------------------------------------------------------

def main():
    contas_final = {}
    for chave, cfg in CONTAS_CONFIG.items():
        pasta = os.path.join(BASE_DRIVE, cfg['pasta'])
        if not os.path.isdir(pasta):
            print(f'[aviso] pasta não encontrada para "{chave}": {pasta} — pulando')
            continue
        d = processar_conta(pasta)
        avisos_si = d.pop('_avisos_sellin', [])

        # trava de segurança: avisa (não impede) se faltar relatório essencial,
        # pra não gerar silenciosamente uma conta "zerada" no dashboard
        essenciais = {'vendas': d['vendas'], 'estoque': d['estoque'],
                      'trafego': d['trafego'], 'margem': d['margem']}
        faltando = [k for k, v in essenciais.items() if not v]
        if faltando:
            print(f'[ATENÇÃO] "{chave}" ({cfg["nome"]}) está SEM dados de: {", ".join(faltando)}. '
                  f'Verifique a pasta {pasta} antes de publicar o dashboard com esta conta.')
        if not d.get('catalogo'):
            print(f'[aviso] "{chave}" ({cfg["nome"]}) sem catalogo.json (nome/imagem/BSR por ASIN) — '
                  f'rode capturar_catalogo.py se quiser essa informação no dashboard.')
        if not d.get('qualidade', {}).get('asins'):
            print(f'[aviso] "{chave}" ({cfg["nome"]}) sem qualidade_catalogo.json (índice de qualidade CDQ) — '
                  f'rode calcular_qualidade_catalogo.py se quiser a aba de qualidade CDQ no dashboard.')
        ql_resumo = d.get('qualidadeListings', {}).get('resumo', {})
        if not ql_resumo.get('totalAsins'):
            print(f'[aviso] "{chave}" ({cfg["nome"]}) sem qualidade_listings.json (status/issues reais da Amazon) — '
                  f'rode capturar_qualidade_listings.py se quiser essa informação no dashboard.')
        else:
            print(f"  qualidade listings: {ql_resumo['totalAsins']} ASINs | "
                  f"{ql_resumo['saudaveis']} sem pendência ({ql_resumo['pctSaudaveis']}%) | "
                  f"{ql_resumo['comErro']} com erro | {ql_resumo['comAviso']} com aviso | "
                  f"{ql_resumo['suprimidos']} suprimidos")
        for av in avisos_si:
            print(f'[sell-in] "{chave}" ({cfg["nome"]}): {av}')

        d['nome'] = cfg['nome']
        d['nota'] = cfg.get('nota', '')
        r = analisar(d)
        if r:
            d['analise'] = r
        d['extras'] = d.get('extras', {'cestaCompras': [], 'termosBusca': [], 'recompra': []})
        contas_final[chave] = d
        print(f"=== {cfg['nome']} ===")
        tot_si = d['sellinMes']
        if tot_si:
            s = lambda campo: sum(v[campo] for v in tot_si.values())
            print(f"  sell-in: {d['totalPOs']} POs | pedido {s('pedido'):,.0f} un | cancelado {s('cancelado'):,.0f} | aceito {s('conf'):,.0f} (válido {s('confValido'):,.0f}) | "
                  f"rejeitado {s('rej'):,.0f} | recebido {s('recebido'):,.0f} | pendente {s('pendente'):,.0f} | "
                  f"ASINs atrasados {len(d['atrasados'])}")
        if r:
            for dg in r['diagnosticos']:
                print(f"  [{dg['impacto']:>12,.2f}] {dg['titulo']} ({dg['qtd']} itens)")
        else:
            print('  (sem dados suficientes para diagnóstico)')

    with open(SAIDA, 'w', encoding='utf-8') as f:
        json.dump(contas_final, f, ensure_ascii=False, separators=(',', ':'))
    print(f'\nSalvo: {SAIDA} ({os.path.getsize(SAIDA):,} bytes)')
    print('Contas processadas:', list(contas_final.keys()))


if __name__ == '__main__':
    main()
