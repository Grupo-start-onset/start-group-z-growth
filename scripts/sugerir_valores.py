# ==================================================================
# sugerir_valores.py
# Le a aba "Corrigível via API" de correcoes_propostas.xlsx e tenta
# preencher uma coluna de SUGESTAO (nunca a coluna "Valor correto
# (preencher)" direto) para CADA atributo faltando (código 18448),
# usando so o nome do produto no catalogo -- e a unica fonte que temos.
#
# São todas sugestões FRACAS: nada aqui é medido de verdade, é chute
# por palavra-chave/regex no título. Fica numa coluna separada,
# claramente marcada -- alguém tem que olhar e copiar pra
# "Valor correto (preencher)" só se achar que está certo.
#
# Por que nao envia direto: peso/dimensao/capacidade nao sao texto
# simples pra Amazon (sao numero+unidade, formato que
# corrigir_listings.py ainda nao monta) -- aqui e so uma DICA em texto
# pra quem for preencher a mao, nao um valor pronto pra API.
#
# Uso: python scripts/sugerir_valores.py
# ==================================================================

import os, re, json
import openpyxl

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PLANILHA = os.path.join(RAIZ, 'correcoes_propostas.xlsx')
COL_SUGESTAO = 'Sugestão fraca (conferir antes de usar)'

RE_ATRIBUTOS_18448 = re.compile(r'envio:\s*(.*?)\.\s*A falta')

# --- extratores por atributo: cada um recebe o nome do produto e devolve
#     um valor sugerido (string) ou None se não achar sinal nenhum ---

MATERIAL_POR_PALAVRA = [
    (r'a[çc]o\s+inox|inox\b', 'Aço Inoxidável'),
    (r'\ba[çc]o\b', 'Aço'),
    (r'\bvidro\b', 'Vidro'),
    (r'\bmadeira\b', 'Madeira'),
    (r'\bbambu\b', 'Bambu'),
    (r'\bpl[áa]stico\b', 'Plástico'),
    (r'\bsilicone\b', 'Silicone'),
    (r'\bcer[âa]mica\b', 'Cerâmica'),
    (r'\bpor?celana\b', 'Porcelana'),
    (r'\balum[íi]nio\b', 'Alumínio'),
    (r'\bcouro\b', 'Couro'),
    (r'\balgod[ãa]o\b', 'Algodão'),
    (r'\bpoli[ée]ster\b', 'Poliéster'),
    (r'\bhelanca\b', 'Helanca (poliéster)'),
    (r'\bmoletom\b', 'Moletom (algodão/poliéster)'),
    (r'\belastano|lycra\b', 'Elastano'),
    (r'\bfibra\s+de\s+vidro\b', 'Fibra de Vidro'),
    (r'\bmelamina\b', 'Melamina'),
    (r'\bcristal\b', 'Cristal'),
    # fraco: shampoo/produto liquido geralmente vem em frasco plastico -- so um chute de contexto
    (r'\bshampoo\b|\bleave-?in\b|\bcondicionador\b|\bm[áa]scara\b.*capilar', 'Plástico (embalagem, chute por categoria)'),
]
MATERIAL_REGEX = [(re.compile(p, re.IGNORECASE), v) for p, v in MATERIAL_POR_PALAVRA]

def sugerir_material(nome):
    for rx, val in MATERIAL_REGEX:
        if rx.search(nome):
            return val
    return None


RE_CAPACIDADE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(ml|l)\b', re.IGNORECASE)

def sugerir_capacity(nome):
    m = RE_CAPACIDADE.search(nome)
    if not m:
        return None
    valor, unidade = m.group(1), m.group(2).lower()
    return f'{valor} {"litros" if unidade == "l" else "mililitros"} (extraído do título)'


RE_DIMENSOES = re.compile(r'(\d+(?:[.,]\d+)?)\s*(?:cm)?\s*x\s*(\d+(?:[.,]\d+)?)\s*(?:cm)?\s*x\s*(\d+(?:[.,]\d+)?)\s*cm', re.IGNORECASE)

def sugerir_dimensoes(nome):
    m = RE_DIMENSOES.search(nome)
    if not m:
        return None
    a, b, c = m.groups()
    return f'{a} x {b} x {c} cm (extraído do título — ORDEM comprimento/largura/altura não garantida, conferir)'


TIMES_E_TEMAS = ['Real Madrid', 'Manchester City', 'Barcelona', 'Flamengo', 'Corinthians',
                  'Palmeiras', 'São Paulo', 'Santos', 'Vasco', 'Grêmio', 'Internacional']

def sugerir_theme(nome):
    for t in TIMES_E_TEMAS:
        if t.lower() in nome.lower():
            return f'{t} (nome de time encontrado no título)'
    return None


ANIMAIS = [('cachorro|c[ãa]o\\b|canino|pet\\b', 'Cachorro'), ('gato|felino', 'Gato')]
ANIMAIS_REGEX = [(re.compile(p, re.IGNORECASE), v) for p, v in ANIMAIS]

def sugerir_animal_theme(nome):
    for rx, val in ANIMAIS_REGEX:
        if rx.search(nome):
            return val
    return None


AROMAS = ['aloe vera', 'argan', 'coco', 'coconut', 'lavanda', 'baunilha', 'verniz', 'mandioca']

def sugerir_scent(nome):
    baixo = nome.lower()
    for a in AROMAS:
        if a in baixo:
            return f'{a.title()} (palavra encontrada no título — pode ser ingrediente, não aroma; conferir)'
    return None


COMODOS = [('cozinha', 'Cozinha'), ('banheiro', 'Banheiro'), ('quarto', 'Quarto'),
           ('sala\\b', 'Sala'), ('escrit[óo]rio', 'Escritório'), ('[áa]rea\\s+externa|jardim', 'Área externa')]
COMODOS_REGEX = [(re.compile(p, re.IGNORECASE), v) for p, v in COMODOS]

def sugerir_room_type(nome):
    for rx, val in COMODOS_REGEX:
        if rx.search(nome):
            return val
    return None


# atributo (como aparece na mensagem da Amazon) -> funcao extratora
EXTRATORES = {
    'material': sugerir_material,
    'capacity': sugerir_capacity,
    'item_weight': sugerir_dimensoes,               # peso raramente vem no título; dimensão às vezes ajuda a achar o peso perto -- fraco mesmo assim, deixa a func tentar achar algo perto
    'item_depth_width_height': sugerir_dimensoes,
    'item_length_width_height': sugerir_dimensoes,
    'item_length_width': sugerir_dimensoes,
    'theme': sugerir_theme,
    'animal_theme': sugerir_animal_theme,
    'scent': sugerir_scent,
    'room_type': sugerir_room_type,
}
# item_weight não deveria usar dimensão como "sugestão de peso" -- é um extrator errado; melhor não sugerir nada
del EXTRATORES['item_weight']


def main():
    if not os.path.exists(PLANILHA):
        print(f'Não achei {PLANILHA} -- rode scripts/classificar_correcoes.py primeiro.')
        return

    wb = openpyxl.load_workbook(PLANILHA)
    ws = wb['Corrigível via API']
    cabecalho = [c.value for c in ws[1]]
    if COL_SUGESTAO not in cabecalho:
        ws.cell(row=1, column=len(cabecalho) + 1, value=COL_SUGESTAO)
        cabecalho.append(COL_SUGESTAO)
    idx = {nome: i for i, nome in enumerate(cabecalho)}

    total_linhas, linhas_com_alguma_sugestao = 0, 0
    total_atributos, atributos_sugeridos = 0, 0
    sem_extrator = {}

    for row in ws.iter_rows(min_row=2):
        codigo = row[idx['Código']].value
        mensagem = row[idx['Mensagem da Amazon']].value or ''
        if str(codigo) != '18448':
            continue
        m = RE_ATRIBUTOS_18448.search(mensagem)
        if not m:
            continue
        atributos = [a.strip() for a in m.group(1).split(',') if a.strip()]
        produto = row[idx['Produto']].value or ''

        total_linhas += 1
        total_atributos += len(atributos)
        partes = []
        for attr in atributos:
            extrator = EXTRATORES.get(attr)
            if not extrator:
                sem_extrator[attr] = sem_extrator.get(attr, 0) + 1
                continue
            valor = extrator(produto)
            if valor:
                partes.append(f'{attr}={valor}')
                atributos_sugeridos += 1

        if partes:
            linhas_com_alguma_sugestao += 1
            ws.cell(row=row[0].row, column=idx[COL_SUGESTAO] + 1, value='; '.join(partes))

    wb.save(PLANILHA)

    print(f'Linhas código 18448: {total_linhas}')
    print(f'  com pelo menos 1 sugestão: {linhas_com_alguma_sugestao}')
    print(f'Atributos faltando no total: {total_atributos}')
    print(f'  com sugestão (fraca): {atributos_sugeridos}')
    print(f'  sem nenhum sinal disponível: {total_atributos - atributos_sugeridos}')
    print()
    print('Atributos sem extrator implementado (nenhum sinal possível a partir só do nome):')
    for attr, n in sorted(sem_extrator.items(), key=lambda x: -x[1]):
        print(f'  {n:4d}  {attr}')
    print(f'\nSalvo: {PLANILHA} (coluna "{COL_SUGESTAO}")')


if __name__ == '__main__':
    main()
