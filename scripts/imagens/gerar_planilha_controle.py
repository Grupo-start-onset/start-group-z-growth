"""Gera a planilha de controle de imagens da New Pet a partir dos listings ao vivo."""
import json, re, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.comments import Comment

rows_json, out = sys.argv[1], sys.argv[2]
rows = json.load(open(rows_json, encoding='utf-8'))

F = 'Arial'
H_FILL = PatternFill('solid', fgColor='1D1D1F')
LOCK_FILL = PatternFill('solid', fgColor='EFEFF2')
IN_FILL = PatternFill('solid', fgColor='FFF2CC')
ACC = 'E8711C'
thin = Side(style='thin', color='D0D0D6')
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def tipo(nome):
    n = nome.lower()
    if 'ração' in n or 'sachê' in n:
        return 'Ração'
    if any(k in n for k in ('granulado', 'tapete', 'cata caca')):
        return 'Higiene'
    return 'Petisco'


def peso(nome, size):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|g)\b', nome, re.I)
    if m:
        return f"{m.group(1).replace('.', ',')} {m.group(2).lower()}"
    m = re.search(r'(\d+)\s*(un|unidades)', nome, re.I)
    if m:
        return f'{m.group(1)} un.'
    m = re.search(r'(\d+\s*x\s*\d+\s*cm)', nome, re.I)
    return m.group(1) if m else (size or '')


def peso_kg(p):
    m = re.match(r'([\d,]+) (kg|g)', p)
    if not m:
        return 0
    v = float(m.group(1).replace(',', '.'))
    return v if m.group(2) == 'kg' else v / 1000


# famílias e EAN de referência sugerido (maior embalagem da família)
fam_nome = {}
for r in rows:
    r['tipo'] = tipo(r['nome'])
    r['peso'] = peso(r['nome'], r['size'])
fams = {}
for r in rows:
    if r['parent']:
        fams.setdefault(r['parent'], []).append(r)
for k, membros in fams.items():
    ref = max(membros, key=lambda r: peso_kg(r['peso']))
    base = re.sub(r'\s*-\s*Pacote.*$|\s*-\s*[\d,]+\s*kg$', '', ref['nome']).strip()
    for r in membros:
        r['familia'] = base
        r['ref'] = '' if r is ref else ref['ean']
for r in rows:
    r.setdefault('familia', '')
    r.setdefault('ref', '')

ordem_tipo = {'Ração': 0, 'Petisco': 1, 'Higiene': 2}
rows.sort(key=lambda r: (ordem_tipo[r['tipo']], r['familia'] or 'zz' + r['nome'], -peso_kg(r['peso'])))

wb = Workbook()

# ---------------------------------------------------------------- INSTRUÇÕES
ws = wb.active
ws.title = 'INSTRUÇÕES'
ws.sheet_view.showGridLines = False
ws.column_dimensions['A'].width = 3
ws.column_dimensions['B'].width = 30
ws.column_dimensions['C'].width = 95
lin = [
    ('t', 'PLANILHA DE CONTROLE · IMAGENS AMAZON · NEW PET'),
    ('s', 'Acompanha o "Guia de Imagens Amazon – New Pet". Produtos e EANs puxados do cadastro da New Pet na Amazon em 10/10/2026.'),
    ('', ''),
    ('h', 'Como usar'),
    ('k', '1. Coloque esta planilha', 'Dentro da pasta "NEWPET - IMAGENS AMAZON" no Google Drive (Arquivo → Importar ou arrastar o arquivo e abrir com Google Planilhas). A mesma pasta onde ficam as imagens, sem subpastas.'),
    ('k', '2. Aba PRODUTOS', 'Uma linha por produto à venda. Escolha o Modelo de A+ (A ou B) e confira a coluna "A+ igual ao EAN" (já sugerida: tamanhos do mesmo produto usam o A+ do maior tamanho).'),
    ('k', '3. Aba ARQUIVOS', 'A lista exata de arquivos que cada produto precisa, com o nome pronto. Copie o nome da coluna "Nome exato do arquivo" ao salvar a imagem e marque o Status como "Na pasta" quando ela estiver no Drive.'),
    ('k', '4. Aba MODELOS', 'O que mostrar em cada posição e o tamanho de cada imagem, para a ração e para petiscos e higiene. Consulta apenas.'),
    ('k', '5. Avise a START', 'Quando a coluna "Completo?" da aba PRODUTOS estiver "SIM" para os produtos do lote. "Completo" considera as imagens obrigatórias; as recomendadas aparecem em coluna própria e devem ser enviadas sempre que possível.'),
    ('', ''),
    ('h', 'Cores'),
    ('in', 'Amarelo', 'Preencher ou escolher (Modelo de A+, A+ igual ao EAN, Status, Observações).'),
    ('lk', 'Cinza', 'Dados do cadastro e fórmulas. Não alterar: são eles que garantem que a imagem vai para o produto certo.'),
    ('', ''),
    ('h', 'Regras dos nomes de arquivo'),
    ('k', 'Formato', 'EAN.CÓDIGO.jpg  →  exemplo: 7898968541504.MAIN.jpg (separado por ponto, código em maiúsculas, sem espaços).'),
    ('k', 'Não renomear', 'Use exatamente o nome da aba ARQUIVOS. Não acrescente sabor, peso, "final", "(1)" ou "cópia".'),
    ('k', 'Formato da imagem', 'Galeria: JPG 2000 × 2000 px, RGB. A+: JPG ou PNG no tamanho exato indicado.'),
    ('k', 'Extras e vídeo', 'Opcionais: EAN.EXTRA1.jpg, EAN.EXTRA2.jpg e EAN.VIDEO.mp4 podem ir para a pasta sem constar nesta planilha.'),
    ('k', 'Textos', 'Não é preciso enviar textos. Título, bullets, descrição e textos do A+ são criados pela START. De vocês, só o texto desenhado dentro das imagens.'),
    ('', ''),
    ('h', 'Atenção'),
    ('k', 'Palito 8" Rígido 10 un.', 'Cadastrado na Amazon com código de 14 dígitos (17908591301158). Usar esse código no nome dos arquivos, exatamente como está na aba ARQUIVOS.'),
    ('k', 'Produto faltando?', 'Se algum produto à venda não aparece aqui, ou um EAN não corresponde à embalagem, avise a START antes de produzir as imagens.'),
]
r = 2
for item in lin:
    kind = item[0]
    if kind == 't':
        ws.cell(r, 2, item[1]).font = Font(name=F, size=16, bold=True)
    elif kind == 's':
        ws.cell(r, 2, item[1]).font = Font(name=F, size=10, color='5B5B63')
    elif kind == 'h':
        ws.cell(r, 2, item[1]).font = Font(name=F, size=12, bold=True, color=ACC)
    elif kind in ('k', 'in', 'lk'):
        a = ws.cell(r, 2, item[1]); b = ws.cell(r, 3, item[2])
        a.font = Font(name=F, size=10, bold=True); b.font = Font(name=F, size=10)
        b.alignment = Alignment(wrap_text=True, vertical='top'); a.alignment = Alignment(vertical='top')
        if kind == 'in':
            a.fill = IN_FILL
        if kind == 'lk':
            a.fill = LOCK_FILL
        ws.row_dimensions[r].height = 28
    r += 1

# ---------------------------------------------------------------- MODELOS
wm = wb.create_sheet('MODELOS')
G = 'Galeria'
gal = [
    ('MAIN', 'Capa (posição 1)', 'Embalagem de frente, fundo branco puro, 85% da área, nada adicionado', 'Embalagem de frente, fundo branco puro, 85% da área, nada adicionado', 'SIM'),
    ('PT01', 'Galeria · posição 2', 'Grande diferencial da linha (número ou promessa forte + grão e ingrediente)', 'Grande diferencial (ex.: natural, biodegradável, perfumado)', 'SIM'),
    ('PT02', 'Galeria · posição 3', 'Benefícios com ícones (4 a 6, impressos na embalagem) + ingrediente', 'Benefícios com ícones (4 a 6, impressos na embalagem)', 'SIM'),
    ('PT03', 'Galeria · posição 4', 'Formato e tamanho do grão, com medida em mm e referência de tamanho', 'Detalhe e tamanho real (petisco, grânulo ou tapete aberto), com medidas', 'SIM'),
    ('PT04', 'Galeria · posição 5', 'Quantidade diária por peso do cão/gato (números idênticos à embalagem)', 'Modo de uso (como oferecer o petisco / como usar o produto)', 'SIM'),
    ('PT05', 'Galeria · posição 6', 'Transição alimentar dia a dia (igual ao verso da embalagem)', 'Quantidade por dia ou rendimento do pacote', 'Recomendada'),
    ('PT06', 'Galeria · posição 7', 'Composição e níveis de garantia em letra grande', 'Composição/níveis de garantia (petiscos) ou especificações (higiene)', 'SIM'),
    ('PT07', 'Galeria · posição 8', 'Emocional / momento de uso (pet do porte certo, pote cheio)', 'Emocional / momento de uso', 'Recomendada'),
    ('PT08', 'Galeria · posição 9', 'Linha da marca ou embalagem anterior × nova', 'Linha da marca ("conheça também")', 'Recomendada'),
]
aplus = [
    # código, (A: onde, ração, outros, tamanho), (B: onde, ração, outros, tamanho)
    ('AP01', ('A+ · Módulo 1 · Banner', 'Embalagem + pet + ingredientes, com o nome da linha', 'Produto + pet, com o nome da linha', '970 × 600'),
             ('A+ · Módulo 1 · Banner', 'Cena principal da linha', 'Cena principal da linha', '970 × 600')),
    ('AP02', ('A+ · Módulo 2 · Texto sobreposto', 'Principal diferencial; deixar o lado direito limpo', 'Principal diferencial; deixar o lado direito limpo', '970 × 300'),
             ('A+ · Módulo 2 · Imagem com destaques', 'Pacote ou grão em destaque', 'Produto em destaque', '300 × 300')),
    ('AP03', ('A+ · Módulo 3 · Benefício 1 de 4', 'Foto/ilustração do benefício 1', 'Foto/ilustração do benefício 1', '220 × 200'),
             ('A+ · Módulo 3 · Imagem 1 de 3', 'Ingrediente 1 (ex.: frango)', 'Benefício 1', '300 × 300')),
    ('AP04', ('A+ · Módulo 3 · Benefício 2 de 4', 'Foto/ilustração do benefício 2', 'Foto/ilustração do benefício 2', '220 × 200'),
             ('A+ · Módulo 3 · Imagem 2 de 3', 'Ingrediente 2 (ex.: arroz)', 'Benefício 2', '300 × 300')),
    ('AP05', ('A+ · Módulo 3 · Benefício 3 de 4', 'Foto/ilustração do benefício 3', 'Foto/ilustração do benefício 3', '220 × 200'),
             ('A+ · Módulo 3 · Imagem 3 de 3', 'Ingrediente 3 (ex.: linhaça)', 'Benefício 3', '300 × 300')),
    ('AP06', ('A+ · Módulo 3 · Benefício 4 de 4', 'Foto/ilustração do benefício 4', 'Foto/ilustração do benefício 4', '220 × 200'),
             ('A+ · Módulo 4 · Texto sobreposto', 'Momento de uso; deixar o lado direito limpo', 'Momento de uso; deixar o lado direito limpo', '970 × 300')),
    ('AP07', ('A+ · Módulo 4 · Especificações', 'Grão ou pacote em destaque', 'Produto em destaque', '300 × 300'),
             ('Não usado no modelo B', '-', '-', '-')),
    ('COMP', ('A+ · Tabela comparativa', 'Pacote na vertical, sem fundo colorido', 'Produto na vertical, sem fundo colorido', '150 × 300'),
             ('A+ · Tabela comparativa', 'Pacote na vertical, sem fundo colorido', 'Produto na vertical, sem fundo colorido', '150 × 300')),
]
mhead = ['Código', 'Modelo A · Onde entra', 'Modelo A · O que mostrar (Ração)', 'Modelo A · O que mostrar (Petiscos e higiene)', 'Modelo A · Tamanho (px)',
         'Modelo B · Onde entra', 'Modelo B · O que mostrar (Ração)', 'Modelo B · O que mostrar (Petiscos e higiene)', 'Modelo B · Tamanho (px)', 'Obrigatória?']
wm['A1'] = 'O que mostrar em cada arquivo · consulta (não alterar). Na galeria, os modelos A e B são iguais; mudam só as imagens do A+.'
wm['A1'].font = Font(name=F, size=10, italic=True, color='5B5B63')
MODEL_COUNT = len(gal) + len(aplus)
for c, h in enumerate(mhead, 1):
    cell = wm.cell(2, c, h)
for i, (cod, onde, rac, out_, obr) in enumerate(gal):
    vals = [cod, onde, rac, out_, '2000 × 2000', onde, rac, out_, '2000 × 2000', obr]
    for c, v in enumerate(vals, 1):
        wm.cell(3 + i, c, v)
for j, (cod, a, b) in enumerate(aplus):
    rr = 3 + len(gal) + j
    obr = 'SIM' if cod == 'COMP' else 'Conforme modelo'
    vals = [cod, *a, *b, obr]
    for c, v in enumerate(vals, 1):
        wm.cell(rr, c, v)
MLAST = 2 + MODEL_COUNT
widths = [9, 26, 52, 52, 14, 30, 40, 40, 14, 16]
for c, w in enumerate(widths, 1):
    wm.column_dimensions[chr(64 + c)].width = w

# ---------------------------------------------------------------- PRODUTOS
wp = wb.create_sheet('PRODUTOS', 1)
phead = ['Nº', 'EAN', 'SKU', 'ASIN', 'Produto (cadastro Amazon)', 'Tipo', 'Família (mesmo produto, outros tamanhos)', 'Peso / tamanho',
         'Modelo de A+', 'A+ igual ao EAN', 'Obrigatórias (total)', 'Obrigatórias na pasta', 'Recomendadas na pasta', 'Completo?', 'Observações']
wp['A1'] = 'PRODUTOS · New Pet · uma linha por produto à venda (cadastro Amazon em 10/10/2026)'
wp['A1'].font = Font(name=F, size=12, bold=True)
wp['A2'] = 'Amarelo = preencher/escolher · Cinza = cadastro e fórmulas, não alterar. "A+ igual ao EAN" já vem sugerido (tamanhos menores usam o A+ do maior); apague para o produto ter A+ próprio.'
wp['A2'].font = Font(name=F, size=9, italic=True, color='5B5B63')
HR = 3
for c, h in enumerate(phead, 1):
    wp.cell(HR, c, h)
P0 = HR + 1
PL = P0 + len(rows) - 1
for i, r in enumerate(rows):
    rr = P0 + i
    vals = [i + 1, r['ean'], r['sku'], r['asin'], r['nome'], r['tipo'], r['familia'], r['peso'], 'A', r['ref'] or None]
    for c, v in enumerate(vals, 1):
        cell = wp.cell(rr, c, v)
    wp.cell(rr, 2).number_format = '@'
    wp.cell(rr, 10).number_format = '@'
    wp.cell(rr, 11, f'=COUNTIFS(ARQUIVOS!$A:$A,$B{rr},ARQUIVOS!$J:$J,"SIM")')
    wp.cell(rr, 12, f'=COUNTIFS(ARQUIVOS!$A:$A,$B{rr},ARQUIVOS!$J:$J,"SIM",ARQUIVOS!$K:$K,"Na pasta")')
    wp.cell(rr, 13, f'=COUNTIFS(ARQUIVOS!$A:$A,$B{rr},ARQUIVOS!$J:$J,"RECOMENDADA",ARQUIVOS!$K:$K,"Na pasta")&" de "&COUNTIFS(ARQUIVOS!$A:$A,$B{rr},ARQUIVOS!$J:$J,"RECOMENDADA")')
    wp.cell(rr, 14, f'=IF(L{rr}>=K{rr},"SIM","NÃO")')
    if r['sku'] == '1238':
        wp.cell(rr, 15, 'Código de 14 dígitos no cadastro: usar exatamente este nos arquivos')
    elif not r['familia'] and r['tipo'] != 'Ração':
        pass
pw = [5, 17, 15, 13, 62, 9, 44, 13, 12, 17, 12, 12, 13, 11, 40]
for c, w in enumerate(pw, 1):
    wp.column_dimensions[chr(64 + c)].width = w
wp.cell(HR, 9).comment = Comment('A = Essencial (7 imagens + COMP). B = Destaques (6 imagens + COMP). Ver guia, seção 6.', 'START')
wp.cell(HR, 10).comment = Comment('Preencha com o EAN do produto cujo A+ este vai repetir. Vazio = este produto tem A+ próprio e precisa das imagens AP.', 'START')

dv_mod = DataValidation(type='list', formula1='"A,B"', allow_blank=False, showErrorMessage=True,
                        errorTitle='Modelo de A+', error='Escolha A ou B.')
dv_ref = DataValidation(type='list', formula1=f'=$B${P0}:$B${PL}', allow_blank=True, showErrorMessage=True,
                        errorTitle='A+ igual ao EAN', error='Use um EAN da coluna B (ou deixe vazio).')
wp.add_data_validation(dv_mod); wp.add_data_validation(dv_ref)
dv_mod.add(f'I{P0}:I{PL}'); dv_ref.add(f'J{P0}:J{PL}')

# ---------------------------------------------------------------- ARQUIVOS
wa = wb.create_sheet('ARQUIVOS', 2)
ahead = ['EAN', 'Produto', 'Peso / tamanho', 'Código', 'Nome exato do arquivo', 'Onde entra', 'O que mostrar', 'Tamanho (px)',
         'Obrigatória?', 'Necessário?', 'Status', 'Observações']
wa['A1'] = 'ARQUIVOS · lista exata de imagens por produto. Copie o nome da coluna E e marque o Status quando a imagem estiver na pasta.'
wa['A1'].font = Font(name=F, size=12, bold=True)
wa['A2'] = 'Linhas com "NÃO" em Necessário? não precisam de arquivo (o produto usa o A+ de outro EAN, ou o código não existe no modelo escolhido).'
wa['A2'].font = Font(name=F, size=9, italic=True, color='5B5B63')
for c, h in enumerate(ahead, 1):
    wa.cell(HR, c, h)
codes = [g[0] for g in gal] + [a[0] for a in aplus]
PR = f'PRODUTOS!$B${P0}:$B${PL}'
MR = f'MODELOS!$A$3:$A${MLAST}'
rr = HR + 1
for r in rows:
    for cod in codes:
        m = f'MATCH($A{rr},{PR},0)'
        modelo = f'INDEX(PRODUTOS!$I${P0}:$I${PL},{m})'
        tp = f'INDEX(PRODUTOS!$F${P0}:$F${PL},{m})'
        ref = f'INDEX(PRODUTOS!$J${P0}:$J${PL},{m})'
        mm = f'MATCH($D{rr},{MR},0)'

        def col(a, b):
            return f'IF({modelo}="B",INDEX(MODELOS!${b}$3:${b}${MLAST},{mm}),INDEX(MODELOS!${a}$3:${a}${MLAST},{mm}))'
        wa.cell(rr, 1, r['ean']).number_format = '@'
        wa.cell(rr, 2, f'=INDEX(PRODUTOS!$E${P0}:$E${PL},{m})')
        wa.cell(rr, 3, f'=INDEX(PRODUTOS!$H${P0}:$H${PL},{m})')
        wa.cell(rr, 4, cod)
        wa.cell(rr, 5, f'=$A{rr}&"."&$D{rr}&".jpg"')
        wa.cell(rr, 6, '=' + col('B', 'F'))
        wa.cell(rr, 7, f'=IF({tp}="Ração",{col("C", "G")},{col("D", "H")})')
        wa.cell(rr, 8, '=' + col('E', 'I'))
        wa.cell(rr, 9, f'=INDEX(MODELOS!$J$3:$J${MLAST},{mm})')
        wa.cell(rr, 10, f'=IF(LEFT($D{rr},2)<>"AP",IF($I{rr}="SIM","SIM","RECOMENDADA"),IF({ref}<>"","NÃO (usa o A+ do EAN "&{ref}&")",IF(AND({modelo}="B",$D{rr}="AP07"),"NÃO (modelo B)","SIM")))')
        wa.cell(rr, 11, 'Pendente')
        rr += 1
AL = rr - 1
dv_st = DataValidation(type='list', formula1='"Pendente,Na pasta"', allow_blank=False)
wa.add_data_validation(dv_st); dv_st.add(f'K{HR+1}:K{AL}')
aw = [17, 52, 13, 8, 30, 32, 60, 13, 13, 30, 12, 30]
for c, w in enumerate(aw, 1):
    wa.column_dimensions[chr(64 + c)].width = w

# ---------------------------------------------------------------- estilos comuns
def estilo(ws, ncol, first, last, inputs):
    for c in range(1, ncol + 1):
        h = ws.cell(HR if ws.title != 'MODELOS' else 2, c)
        h.font = Font(name=F, size=10, bold=True, color='FFFFFF'); h.fill = H_FILL
        h.alignment = Alignment(wrap_text=True, vertical='center'); h.border = BORDER
    for row in ws.iter_rows(min_row=first, max_row=last, max_col=ncol):
        for cell in row:
            cell.font = Font(name=F, size=9)
            cell.border = BORDER
            cell.alignment = Alignment(vertical='top', wrap_text=cell.column_letter in ('B', 'C', 'D', 'E', 'F', 'G', 'H') and ws.title == 'MODELOS')
            cell.fill = IN_FILL if cell.column in inputs else LOCK_FILL


estilo(wp, len(phead), P0, PL, {9, 10, 15})
estilo(wa, len(ahead), HR + 1, AL, {11, 12})
estilo(wm, len(mhead), 3, MLAST, set())
for ws_, last in ((wp, PL), (wa, AL)):
    ws_.row_dimensions[HR].height = 30
for c in (2, 5):
    for rrr in range(P0, PL + 1):
        pass
for rrr in range(HR + 1, AL + 1):
    wa.cell(rrr, 5).font = Font(name='Courier New', size=9, bold=True)
for rrr in range(P0, PL + 1):
    wp.cell(rrr, 2).font = Font(name='Courier New', size=9, bold=True)
wm.row_dimensions[2].height = 30

green = PatternFill('solid', fgColor='D9F0E1'); red = PatternFill('solid', fgColor='F8DADA')
wp.conditional_formatting.add(f'N{P0}:N{PL}', FormulaRule(formula=[f'$N{P0}="SIM"'], fill=green, font=Font(name=F, bold=True, color='1F7A3F')))
wp.conditional_formatting.add(f'N{P0}:N{PL}', FormulaRule(formula=[f'$N{P0}="NÃO"'], fill=red, font=Font(name=F, color='B3261E')))
grey_txt = Font(name=F, color='9A9AA2')
wa.conditional_formatting.add(f'A{HR+1}:L{AL}', FormulaRule(formula=[f'LEFT($J{HR+1},3)="NÃO"'], font=grey_txt))
wa.conditional_formatting.add(f'K{HR+1}:K{AL}', FormulaRule(formula=[f'$K{HR+1}="Na pasta"'], fill=green))

for ws_, ref_ in ((wp, f'A{HR}:{chr(64+len(phead))}{PL}'), (wa, f'A{HR}:{chr(64+len(ahead))}{AL}')):
    ws_.auto_filter.ref = ref_
    ws_.freeze_panes = ws_.cell(HR + 1, 3)
wm.freeze_panes = 'B3'
wb.active = 0
wb.save(out)
print('linhas produtos', len(rows), 'linhas arquivos', AL - HR)
