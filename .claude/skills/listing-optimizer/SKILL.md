---
name: listing-optimizer
description: Regras oficiais da Amazon (e política interna do grupo) para título, bullet points, descrição e imagens de listings (SP-API Listings Items), validadas contra os 7 documentos oficiais da Amazon Vendor Brasil. Usadas para diagnosticar e reescrever conteúdo de catálogo com segurança. Use sempre que for revisar, pontuar ou reescrever título/bullets/descrição/imagens de ASINs de qualquer conta do grupo.
---

# Listing Optimizer

Regras para melhorar título, bullet points, descrição e imagens sem depender
de "bom senso" solto — toda correção de texto se baseia nisto, no schema
oficial por categoria, e nos atributos reais já cadastrados do próprio ASIN.

## Fonte de verdade — nesta ordem

1. **Formulário vivo**: https://claude.ai/artifact/SvqVXWEhZiHGyNKxkVj8HW —
   tem as 42 regras validadas (com status e fonte, documento + página, de
   cada uma), os 32 ASINs de referência do grupo e os 32 links de modelo.
   Releia esse formulário no início de qualquer trabalho de listing; ele é
   editável e pode ter sido atualizado desde a última vez. Ler via
   `ArtifactData` (`action: "list"`, `collection: "regras"` /
   `"asinsReferencia"` / `"links"` / `"documentos"`).
2. **Atributos reais do próprio ASIN** (`search_listings_items` com
   `includedData=['attributes']`) — nunca inventar característica, usar
   medida, cor, material, galhos/unidades etc. que já estão no cadastro.
   Dimensão de **embalagem** (`item_package_dimensions`) não é o tamanho do
   produto montado — nunca usar como se fosse.
3. **Schema da categoria** (`ProductTypeDefinitions`) — limites de
   caracteres e nome dos campos mudam por `productType` (confirmado:
   `VASE` tem `item_name.maxLength=200`, `bullet_point` até 10 itens de
   700 caracteres, campo de descrição pode se chamar `rtip_product_description`
   **ou** haver mais de um campo com "descri" no nome por categoria —
   sempre priorizar `rtip_product_description` quando existir, nunca pegar
   o primeiro por ordem alfabética/dict, isso já causou falso positivo de
   "sem descrição" numa conta inteira em 06/10/2026).

```python
from sp_api.api import ProductTypeDefinitions
r = api.get_definitions_product_type(productType=TIPO, marketplaceIds=[MARKETPLACE_ID], requirements='LISTING')
url = r.payload['schema']['link']['resource']
schema = json.loads(urllib.request.urlopen(url).read())
props = schema['properties']
```

## Regras de título (validadas em 06/10/2026 contra o Guia Completo CDQ)

- **Estrutura**: Marca + Tipo de produto + Característica principal +
  Especificações (cor, tamanho, quantidade). Confirmado duas vezes no Guia
  CDQ (estrutura recomendada e Matriz de Controle).
  Ex.: `Rio Master Árvore de Natal Verde com 120 Galhos em PVC`.
- **Comprimento, dois critérios diferentes, não confundir**:
  - 10 a 170 caracteres = nota máxima de comprimento no CDQ. 171 a 200 =
    aceitável mas pode cortar em mobile. Acima de 200 ou abaixo de 10 =
    não permitido, risco de supressão do ASIN.
  - **Grau A** (nota máxima geral) exige especificamente até **75**
    caracteres, mais baixa redundância e boa completude — é um critério à
    parte, não o teto geral. Mirar 75 quando o produto permitir, aceitar
    até 170 sem perder nota de comprimento.
- Title Case (primeira letra de cada palavra maiúscula); nunca CAIXA ALTA.
- Usar numerais no lugar de palavras ("2" em vez de "dois").
- Evitar palavra repetida em excesso (keyword stuffing, defeito de Grau C)
  — a Amazon não documenta um número exato de repetições, usar bom senso.
- Proibido: Frete Grátis, Melhor Preço, Promoção, Oferta, "qualidade 100%
  garantida", qualquer frase promocional.
- Proibido símbolos (®, ©, !, $, *, Æ), emojis, informação enganosa, texto
  em outro idioma sem necessidade.
- Nunca genérico ("Tênis Nike" pontua baixo) — precisa ser descritivo.
- Nenhum título repetido entre SKUs distintos (política interna do grupo).

## Regras de bullet points

- 3 a 5 bullets por SKU; menos de 3 perde nota no CDQ.
- Iniciar cada bullet com uma palavra-chave em letras maiúsculas, seguida
  de frase curta de benefício.
- Até 200 caracteres por bullet (recomendado).
- Cada bullet responde uma dúvida de compra: uso, medida, compatibilidade,
  conteúdo da embalagem, cuidado ou garantia (garantia só se estiver nos
  dados — nunca inventar).
- Não repetir no bullet o que já está no título.
- Sem linguagem promocional, emojis ou caracteres especiais.
- Nenhum bullet repetido entre SKUs, mesmo dentro de uma família grande.
- Bullet com só o nome de uma peça/embalagem ("FRASCOS", "BISNAGA") não é
  bullet de verdade — reescrever com uma característica real do produto
  (visto em 198 ASINs da Rio Master em 06/10/2026).

## Regras de descrição

- Cerca de 1.500 caracteres, em prosa. **Atenção**: descrição não é um dos
  6 componentes pontuados pelo CDQ (Atributos 30%, Título 25%, Variações
  20%, Imagens 15%, Conteúdo A+ 5%, Bullets 5% = 100%) — a regra de
  caracteres vem só do Manual de Qualidade de Catálogo, não do guia de
  pontuação. Ainda assim seguir, é a orientação oficial de conteúdo.
- Usar apenas funcionalidades, usos e diferenciais presentes nos dados.
  Narrativa de uso (situação, necessidade, solução) é permitida; atributo
  novo inventado na narrativa não é.
- Mesmas proibições do título e dos bullets (termos promocionais, símbolos,
  emojis).
- Evitar alegação terapêutica/medicinal não comprovada em produto cosmético
  ou pet ("trata", "cura", "previne doença") — risco de supressão por
  Amazon ou Anvisa. Baixa urgência se já publicado sem problema até agora;
  priorizar em reescrita nova.

## Regras de imagens

- Mínimo de **1000 px** no lado maior.
- Imagem principal com fundo branco puro (RGB 255, 255, 255).
- **Mínimo de 5 imagens no total** (principal + 4). Os dois documentos
  oficiais divergem entre si — Manual de Qualidade de Catálogo pede 4 além
  da principal (5 no total), Guia CDQ conta 4 no total para nota máxima —
  seguir o mais rigoroso (5) atende aos dois ao mesmo tempo.
- Sem texto, logo ou marca d'água.
- Nomenclatura para upload em massa (ZIP): `EAN.MAIN.jpg` para a principal,
  `EAN.PT01.jpg`, `EAN.PT02.jpg` para as demais.
- Conteúdo A+ só com Brand Registry.

## Conteúdo proibido (qualquer campo)

- Comparação direta com concorrente nomeado, superlativo absoluto, promessa
  de resultado (não encontrado nos 7 documentos oficiais, mantido como
  política interna até confirmação).
- Dado de contato, site externo ou rede social do vendedor.
- Emojis e símbolos decorativos.
- Valor de atributo inventado ou estimado sem autorização — principalmente
  os 6 atributos da Visão Geral do Produto: errado em qualquer um deles
  gera Grau D automático (CDQ, confirmado).

## Processo de uso (diagnóstico → referência → reescrita → revisão → publicação)

1. **Ler o formulário vivo** (link acima) antes de começar, para pegar
   regra nova ou ASIN de referência que tenha sido adicionado.
2. **Buscar a referência da marca antes de reescrever.** O formulário
   (Seção 4, `asinsReferencia`) tem um ASIN de referência por marca do
   grupo, indicado pelo cliente como bem ranqueado/bem escrito. Antes de
   reescrever qualquer item da marca X, puxar o(s) ASIN(s) de referência
   de X com `CatalogItems.get_catalog_item(asin, includedData=['summaries','attributes'])`
   (funciona pra ASIN de qualquer vendedor, não só os nossos) e usar o
   padrão real de comprimento, estrutura e tom como calibração — não só
   seguir o número teórico do CDQ isoladamente.
   **Lição de 06/10/2026 (Rio Master, categoria Natal)**: o CDQ trata 75
   caracteres como critério de Grau A, mas o ASIN de referência do cliente
   (B0FM5YBV67, #3 em Enfeites de Natal) tem título de 179 caracteres, rico
   em especificação real (altura, galhos) e adjetivos de venda. Outros 2
   ASINs de referência da mesma categoria confirmam o padrão (150-200
   caracteres). Título curto demais (54-61 caracteres) ficou mais pobre que
   o padrão real do nicho, mesmo "correto" pelo documento isolado. Sempre
   calibrar pelo exemplo real antes de aplicar o número teórico como teto.
   Se a referência expõe um atributo que falta no nosso cadastro (ex.:
   altura real do produto, que a Rio Master não tinha preenchido, só
   dimensão de embalagem), registrar como pendência para o cliente
   completar o dado — nunca inventar pra igualar à referência.
4. **Diagnóstico**: rodar `scripts/diagnosticar_listing.py <conta> [asin...]`
   — busca título/bullets/descrição atuais + schema da categoria, aponta
   violações objetivas (CAIXA ALTA, acima do limite, termo proibido, menos
   de N bullets, bullet vazio). 100% determinístico, sem IA.
5. **Reescrita**: para os itens com violação, buscar os atributos reais do
   ASIN (`includedData=['attributes']`) e redigir novo
   título/bullets/descrição com dado real, calibrado pela referência da
   marca (passo 2), seguindo a estrutura e os limites acima. Nunca usar
   frase genérica de preenchimento ("decoração deslumbrante e durável")
   no lugar de característica real — isso também viola a regra de
   "título/bullet não genérico". Comprimento: mirar a faixa real observada
   na referência, não só o mínimo teórico de Grau A.
6. **Revisão humana**: apresentar antes/depois em texto ou planilha para
   aprovação — nunca publicar sem essa etapa enquanto o processo for novo.
7. **Publicação**: só após aprovação, usar `patch_listings_item` com
   `op: replace` no atributo alterado (não precisa reenviar o listing
   inteiro, isso é só para o PUT de mudança de categoria). Nunca reenviar
   `cost_price` em conta Vendor.

## O que NÃO fazer

- Não reescrever em lote sem revisão humana (ainda).
- Não assumir limites de caractere sem checar o schema da categoria.
- Não usar bullets pra informação que já tem atributo estruturado próprio.
- Não inventar claims de certificação/aprovação que não foram fornecidos
  pelo cliente.
- Não usar dimensão de embalagem como se fosse tamanho do produto.
- Não escrever título/bullet com frase de preenchimento genérica só para
  substituir um termo proibido — buscar característica real do ASIN.
- Não confundir "faixa ideal de comprimento" (10 a 170) com "critério de
  Grau A" (até 75) — são coisas diferentes, ver seção de título.
