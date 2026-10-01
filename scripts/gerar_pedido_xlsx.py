# ==================================================================
# gerar_pedido_xlsx.py
# Gera um .xlsx por PEDIDO DE COMPRA (PO), no layout de referencia que
# o parceiro usa (logo a esquerda, logo da marca a direita, caixa de
# RESUMO, tabela de itens, rodape) -- so que com o logo da START no
# lugar do logo do parceiro, e o logo da marca/conta no lugar do logo
# do fornecedor.
#
# Usado por notificar_pedidos.py (um .xlsx por PO novo, anexado no
# email). Tambem pode ser chamado direto pra gerar um arquivo avulso.
#
# Campos que o modelo de referencia tem e a gente NAO tem (CNPJ, codigo
# de fornecedor, forma/termos de pagamento) ficam de fora -- preferi
# omitir a linha a inventar um valor.
# ==================================================================

import os, json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
LOGO_START = os.path.join(RAIZ, 'assets', 'start-s-logo.png')

# mesmo mapeamento conta -> logo(s) de assets/logos/ usado no dashboard (app.js, LOGOS).
# Pega sempre o primeiro da lista (logo "principal" da conta); contas sem entrada ficam
# sem logo de marca (so o nome por extenso, em texto).
LOGO_MARCA_CONTA = {
    'alfa_jf':   'treeliss.png',
    'blidshop':  'blidshop.png',
    'conta3':    'orba.png',
    'ozitp':     'kastking.png',
    'jolitex':   'jolitex.png',
    'balboa':    'ligga.png',
    'riomaster': 'riomaster.png',
}

STATUS_PT = {'OPEN': 'Aberto', 'CLOSED': 'Fechado', 'SEM_STATUS': 'Sem status'}
AZUL_START = '1F3864'
CINZA_CLARO = 'F2F2F2'


def _fmt_data(iso):
    if not iso:
        return '—'
    return iso[:10][8:10] + '/' + iso[5:7] + '/' + iso[:4]


def _nome_produto(catalogo, asin):
    return ((catalogo or {}).get(asin) or {}).get('nome') or asin


def gerar_xlsx_pedido(conta_chave, conta_nome, po, catalogo, caminho_saida):
    """po = um registro do bloco `pedidos` do dados_vendor.json (um PO, com `itens`)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"PO {po['po']}"[:31]

    bold = Font(bold=True)
    bold_branco = Font(bold=True, color='FFFFFF')
    titulo_azul = Font(bold=True, size=12, color=AZUL_START)
    fill_azul = PatternFill('solid', fgColor=AZUL_START)
    fill_cinza = PatternFill('solid', fgColor=CINZA_CLARO)
    borda_fina = Border(*[Side(style='thin', color='CCCCCC')] * 4)

    # --- linha 1: logos (START a esquerda, marca a direita) ---
    ws.row_dimensions[1].height = 42
    if os.path.exists(LOGO_START):
        img = XLImage(LOGO_START)
        img.height, img.width = 40, 40 * (img.width / img.height)
        ws.add_image(img, 'A1')
    nome_logo_marca = LOGO_MARCA_CONTA.get(conta_chave)
    caminho_logo_marca = os.path.join(RAIZ, 'assets', 'logos', nome_logo_marca) if nome_logo_marca else None
    if caminho_logo_marca and os.path.exists(caminho_logo_marca):
        img2 = XLImage(caminho_logo_marca)
        img2.height, img2.width = 40, 40 * (img2.width / img2.height)
        ws.add_image(img2, 'E1')
    else:
        ws['E1'] = conta_nome
        ws['E1'].font = titulo_azul

    # --- cabecalho: dados do pedido (esquerda) + RESUMO (direita) ---
    total_itens = len(po.get('itens') or [])
    total_un = (po.get('tot') or {}).get('pedido', 0)
    total_valor = sum((i.get('pedido') or 0) * (i.get('custoUn') or 0) for i in (po.get('itens') or []))

    janela_txt = (f"{_fmt_data(po.get('janelaIni'))} a {_fmt_data(po.get('janelaFim'))}"
                  if po.get('janelaFim') else '—')

    linhas_cabecalho = [
        ('Pedido de compra', po['po'], 'RESUMO', ''),
        ('Conta', conta_nome, 'Itens', total_itens),
        ('Centro de distribuição', po.get('destino') or '—', 'Unidades', f'{total_un:,.0f}'.replace(',', '.')),
        ('Data do pedido', _fmt_data(po.get('data')), 'Valor solicitado',
         f"R$ {total_valor:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')),
        ('Status', STATUS_PT.get(po.get('status'), po.get('status') or '—'), '', ''),
    ]
    r = 3
    for a, b, d, e in linhas_cabecalho:
        if a:
            ws.cell(row=r, column=1, value=a).font = bold
            ws.cell(row=r, column=2, value=b)
        if d:
            ws.cell(row=r, column=5, value=d).font = bold
            ws.cell(row=r, column=6, value=e)
        r += 1

    # Janela de entrega -- destacada (e a data mais acionavel pro cliente: ate quando
    # a Amazon aceita a entrega desse pedido), em linha propria, com fundo laranja.
    ws.cell(row=r, column=1, value='JANELA DE ENTREGA').font = Font(bold=True, color='FFFFFF')
    ws.cell(row=r, column=2, value=janela_txt).font = Font(bold=True, color='FFFFFF', size=12)
    for col in (1, 2, 3):
        ws.cell(row=r, column=col).fill = PatternFill('solid', fgColor='FD984D')
    r += 1

    # --- tabela de itens ---
    r += 1
    linha_cabecalho_tabela = r
    cabecalho = ['ASIN', 'EAN', 'Produto', 'Qtd solicitada', 'Custo unitário', 'Custo total']
    for col, titulo in enumerate(cabecalho, start=1):
        c = ws.cell(row=r, column=col, value=titulo)
        c.font = bold_branco
        c.fill = fill_azul
        c.alignment = Alignment(horizontal='center')
    r += 1
    for item in (po.get('itens') or []):
        qtd = item.get('pedido') or 0
        custo_un = item.get('custoUn') or 0
        ws.cell(row=r, column=1, value=item.get('asin'))
        ws.cell(row=r, column=2, value=item.get('ean') or '')
        ws.cell(row=r, column=3, value=_nome_produto(catalogo, item.get('asin')))
        ws.cell(row=r, column=4, value=qtd)
        ws.cell(row=r, column=5, value=round(custo_un, 2))
        ws.cell(row=r, column=6, value=round(qtd * custo_un, 2))
        if r % 2 == 0:
            for col in range(1, 7):
                ws.cell(row=r, column=col).fill = fill_cinza
        r += 1

    linha_total = r
    ws.cell(row=r, column=1, value=f'TOTAL — {total_itens} item(ns) · {total_un:,.0f} unidade(s)'.replace(',', '.')).font = bold
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.cell(row=r, column=6, value=round(total_valor, 2)).font = bold

    for row in ws.iter_rows(min_row=linha_cabecalho_tabela, max_row=linha_total, min_col=1, max_col=6):
        for cell in row:
            cell.border = borda_fina

    # --- rodape ---
    r += 2
    ws.cell(row=r, column=1, value='Dúvidas ou problemas entre em contato com: comercial@onsetsell.com')
    r += 1
    ws.cell(row=r, column=1, value='START Inteligência Vendor Central').font = Font(bold=True, color=AZUL_START)

    larguras = [16, 16, 48, 14, 14, 14]
    for col, largura in zip(range(1, 7), larguras):
        ws.column_dimensions[get_column_letter(col)].width = largura
    ws.column_dimensions['D'].width = 2  # separador visual entre cabecalho e resumo

    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    wb.save(caminho_saida)
    return caminho_saida


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print('Uso: python gerar_pedido_xlsx.py <conta> <numero_do_po>')
        sys.exit(1)
    chave, numero_po = sys.argv[1], sys.argv[2]
    contas = json.load(open(os.path.join(RAIZ, 'dados_vendor.json'), encoding='utf-8'))
    conta = contas[chave]
    po = next(p for p in conta['pedidos'] if p['po'] == numero_po)
    saida = os.path.join('/tmp', f'Pedido_{numero_po}_{chave}.xlsx')
    gerar_xlsx_pedido(chave, conta.get('nome') or chave, po, conta.get('catalogo'), saida)
    print(f'Salvo: {saida}')
