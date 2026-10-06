---
name: listing-optimizer
description: Regras oficiais da Amazon para título, bullet points e descrição de listings (SP-API Listings Items), usadas para diagnosticar e reescrever conteúdo de catálogo com segurança. Use sempre que for revisar, pontuar ou reescrever título/bullets/descrição de ASINs de qualquer conta do grupo.
---

# Listing Optimizer

Regras para melhorar título, bullet points e descrição de produtos sem
depender de "bom senso" solto — toda correção de texto deve se basear nisto
mais no schema oficial por categoria (ver seção "Fonte de verdade").

## Por que isso existe

Diferente de correção de atributo (marca, imagem, categoria, nível de
pacote — todos com resposta ACCEPTED/INVALID clara da Amazon), texto de
marketing não tem validação binária. A Amazon aceita um título ruim sem
reclamar. Por isso:

1. Toda reescrita segue as regras abaixo, não "parece melhor pra mim".
2. **Nenhuma reescrita vai direto pro ar.** Sempre passa por lote de revisão
   humana antes de publicar via API, pelo menos até o processo provar que é
   confiável (decisão registrada em `PENDENCIAS.md` item 1).

## Fonte de verdade: schema por categoria, não um guia genérico

Os limites de caracteres e até o **nome do campo** variam por `productType`
(confirmado em 06/10/2026: `VASE` tem `item_name.maxLength=200`,
`bullet_point.items.value.maxLength=700`, até 10 bullets, e o campo de
descrição se chama `rtip_product_description` com `maxLength=150000` —
nomes e limites mudam por categoria). Então, antes de reescrever qualquer
item:

```python
from sp_api.api import ProductTypeDefinitions
r = api.get_definitions_product_type(productType=TIPO, marketplaceIds=[MARKETPLACE_ID], requirements='LISTING')
url = r.payload['schema']['link']['resource']
schema = json.loads(urllib.request.urlopen(url).read())
props = schema['properties']
# props['item_name'], props['bullet_point'], e o campo de descricao
# (procurar chave que contenha 'descri' -- nome varia por categoria)
```

Pegue o `maxLength` real de cada campo e os campos obrigatórios ANTES de
escrever — nunca assuma 200/700/5-bullets como regra fixa pra todas as
categorias, use como teto de segurança quando não der pra confirmar.

## Regras de título

- Estrutura recomendada: **Marca + característica principal + tipo de
  produto + atributo-chave (cor/material/tamanho) + quantidade/medida**.
  Ex.: `Pet Clean Shampoo 2 em 1 para Gatos 700ml`.
- Primeira letra de cada palavra maiúscula; **nunca** o título inteiro em
  CAIXA ALTA.
- Sem frases promocionais: "frete grátis", "100% garantido", "melhor
  preço", "oferta", "desconto", etc. — a Amazon remove/suspende por isso.
- Sem caracteres especiais proibidos: `! $ ? _ { } ^ ¬ ¦` e emojis.
- Sem repetir a mesma palavra-chave mais de 2 vezes (contando singular e
  plural como a mesma palavra).
- Sem informação de frete, preço, ou dados do vendedor no título.
- Respeitar o `maxLength` real da categoria (ver schema).

## Regras de bullet points

- Cada bullet cobre **um aspecto específico** do produto (material, uso,
  benefício, dimensão, cuidado) — não é uma lista de palavras-chave.
- Começar com o benefício/característica em destaque, não com "Este
  produto é...".
- Sem CAIXA ALTA no bullet inteiro, sem abreviação forçada só pra caber.
- **Não** usar bullets para: instruções de montagem/cuidado, informação de
  garantia, ou país de origem — esses têm atributo próprio no schema
  (`care_instructions`, `warranty_description`, `country_of_origin` etc.) e
  duplicar em texto livre é redundante e às vezes rejeitado.
- Quantidade: usar o que a categoria permitir (confirmar `maxUniqueItems`
  no schema), tipicamente até 5 bullets bem escritos é melhor do que muitos
  bullets fracos — mais quantidade não compensa bullet fraco.

## Regras de descrição

- Expande o que os bullets resumem: contexto de uso, para quem é indicado,
  o que vem na embalagem, diferenciais frente a alternativas.
- Sem HTML, sem link, sem e-mail/telefone/site do vendedor.
- Sem alegação que a Amazon classifica como não verificável sem prova
  (ex.: "aprovado por veterinários" sem comprovação) — isso é motivo comum
  de supressão de listing em categoria pet/saúde.
- Tom direto, frases curtas — não é texto institucional da marca, é texto
  de decisão de compra.

## Conteúdo proibido (qualquer campo)

- Comparação direta com concorrente nomeado.
- Reivindicação de "#1 em vendas" ou similar sem prêmio oficial da Amazon.
- Qualquer dado de contato, site externo ou rede social do vendedor.
- Linguagem médica/terapêutica não registrada (cura, trata, previne doença)
  em categorias pet/saúde/beleza — risco de remoção por Amazon ou Anvisa.
- Emojis e símbolos decorativos.

## Processo de uso (diagnóstico → reescrita → revisão → publicação)

1. **Diagnóstico**: rodar `scripts/diagnosticar_listing.py <conta> [asin...]`
   — busca título/bullets/descrição atuais + schema da categoria, e
   aponta violações objetivas (CAIXA ALTA, acima do limite, termo
   proibido, menos de N bullets, bullet vazio etc.). Isso é 100%
   determinístico, sem IA — só compara contra o schema e a lista de termos
   proibidos acima.
2. **Reescrita**: para os itens com violação (ou pedidos de melhoria
   específicos), redigir novo título/bullets/descrição seguindo as regras
   acima, respeitando o `maxLength` real da categoria.
3. **Revisão humana**: apresentar antes/depois em texto (ou planilha para
   lotes grandes) para aprovação — nunca publicar sem essa etapa enquanto o
   processo for novo.
4. **Publicação**: só após aprovação, usar `patch_listings_item` com
   `op: replace` no(s) atributo(s) alterado(s) (não precisa reenviar o
   listing inteiro como no PUT de categoria — aqui é PATCH pontual).
   Mesma regra de sempre: nunca reenviar `cost_price` em conta Vendor.

## O que NÃO fazer

- Não reescrever em lote sem revisão humana (ainda).
- Não assumir limites de caractere sem checar o schema da categoria.
- Não usar bullets pra informação que já tem atributo estruturado próprio.
- Não inventar claims de certificação/aprovação que não foram fornecidos
  pelo cliente.
