# Pendências / próximas sessões

## 1. Skill especializado em otimização de conteúdo de listing (título/bullets/descrição)
Ideia do usuário (06/10/2026): em vez de reescrever título/bullets/descrição "no
bom senso", montar um skill dedicado com as regras oficiais da Amazon
documentadas, e usar esse skill como base pra qualquer correção de texto —
mais consistente e auditável do que confiar em reescrita genérica.

Passos sugeridos:
1. Reunir a documentação oficial da Amazon sobre título, bullet points,
   descrição, imagens e conteúdo proibido (Seller Central / Vendor Central
   Style Guide — por categoria, já que as regras de caracteres variam).
2. Criar um skill do projeto com essas regras como referência (parecido com
   o skill `dataviz` já usado nesta sessão).
3. Construir o processo de correção em cima desse skill.
4. Decidir junto, com base na qualidade observada: publica direto via API ou
   passa por uma revisão humana antes (lote semanal, por exemplo) — pelo menos
   na primeira leva, até confiarmos no padrão.

Motivação: diferente das correções de atributo (marca, imagem, categoria,
nível de pacote — todas com resposta ACCEPTED/INVALID clara da Amazon), texto
de marketing não tem essa validação binária. A Amazon aceita um título ruim
sem reclamar, então um processo 100% autônomo rodando todo dia sem revisão
corre risco de piorar listagens sem ninguém perceber (perda de SEO, texto
pior, possível violação de política só percebida depois via supressão).

## 2. JOLITEX — reclassificação de categoria (productType) — PRATICAMENTE CONCLUÍDA
Hoje (06/10/2026), em duas etapas:

**Etapa 1** (sessão anterior, catálogo parcial de ~1.000 ASINs, limite de
paginação da Amazon): 198 ASINs "HOME" reclassificados — 198/198 aceitos.

**Etapa 2** (sessão atual, catálogo COMPLETO): resolvido o teto de 1.000
resultados do `search_listings_items` com paginação por cursor de data
(`sortBy=lastUpdatedDate, sortOrder=ASC` + `lastUpdatedAfter=<máximo da rodada
anterior>`, em múltiplas rodadas) — técnica não documentada pela Amazon,
descoberta por teste nesta sessão. Script: `full_catalog_jolitex_v2.py`.
Resultado: os 1.173 ASINs reais da conta, confirmando 179 ASINs ainda "HOME"
genérico no catálogo completo (vs. os ~281 vistos no catálogo parcial).

Desses 179, reclassificados em duas levas:
- Leva 1 (regras já existentes): 64/64 aceitos.
- Leva 2 (regras novas, ~35 tipos pesquisados e confirmados via
  `search_definitions_product_types` antes de aplicar — SCULPTURE,
  NAPKIN_RING, TRIVET, KITCHEN_KNIFE, STORAGE_HOOK, TOILET_PAPER_HOLDER,
  TOWEL_HOLDER, PITCHER, COFFEE_MAKER, DRYING_RACK, CLEANING_BRUSH, CABINET,
  CLOTHES_RACK, FOOD_STRAINER, BOTTLE_OPENER, FURNITURE_CART,
  PORTABLE_ELECTRONIC_DEVICE_STAND, DISHWARE_BOWL, BEVERAGE_INSULATOR,
  ROTATING_TRAY, THERMOS, HOME_MIRROR, STORAGE_DRAWER, WHISK_UTENSIL,
  SEASONING_MILL, SPOON, BAKING_MAT, FOOD_SPATULA, PASTRY_BASTING_BRUSH,
  BOTTLE_STOPPER, PAPER_CLIP_CLAMP, BAKING_PAN, CUTTING_BOARD, ITEM_CONTAINER,
  SAUTE_FRY_PAN, BASKET, DISHWARE_PLATE, PAPER_TOWEL_HOLDER, TONG_UTENSIL,
  BUTTER_DISH, NAPKIN_HOLDER, TRAY, SHELF, DRAIN_STRAINER, CADDY,
  FOOD_STORAGE_CONTAINER): 103/103 aceitos.

**Total reclassificado nas duas sessões: 365 ASINs, 365/365 aceitos.**

Ficaram de fora (só isso, nada mais pendente nesta frente):
- **12 ASINs "HOME" sem categoria confiável encontrada** mesmo após pesquisa —
  arriscado demais adivinhar e aplicar via PUT sem confirmação. Lista:
  B0FD4FBXH7 (cubo de gelo artificial decorativo), B0FD4V68B3 (colher
  bailarina p/drinks), B0FD56NZKR (kit 4 utensílios de bambu — set
  genérico), B0FD5C9R6S e B0FD5CH2Y5 (variações MEK de itens que a Amazon já
  classificou diferente do esperado — checar manualmente), B0F6959VYD,
  B0FD4X5FPF, B0CJ5L8CQ3, B0F7RVG8PV, B0FD4X6BY6 (variações MEK diversas),
  B0FD57LBHN (tampa antirrespingo — sem tipo "splatter guard" na taxonomia
  BR), B0DJCDCP4G (esteira de bambu p/sofá — categoria ambígua). Resolver
  individualmente numa sessão futura com paciência, ou aceitar que ficam
  "HOME" genérico (não é erro, só não está no nível mais específico possível).

Mecanismo de reclassificação já validado e funcionando (reaproveitar):
- `GET /listings/2021-08-01/items/{sellerId}/{sku}` (via `search_listings_items`
  com `includedData=['attributes']`) pra pegar os atributos atuais.
- `PUT /listings/2021-08-01/items/{sellerId}/{sku}` (`put_listings_item`) com
  `productType` novo + todos os atributos atuais (removendo `cost_price` do
  payload — reenviar custo trava com erro 101202 em conta Vendor Advantage) e
  incluindo `package_level: unit` (a Amazon as vezes passa a exigir esse
  atributo ao mudar de categoria, mesmo que não exigisse antes).

## 3. Rio Master — imagens faltando (132 ASINs sem imagem principal)
Aguardando: ou (a) export do time que cuida do Playbook da Rio Master com os
arquivos originais em alta resolução (JPEG/PNG, não webp) dos ~132 SKUs
listados, ou (b) acesso mais direto ao Playbook pra automatizar a busca.
Mensagem de pedido já foi redigida nesta sessão (contém a lista completa dos
132 SKUs).

## 4. Card "Venda própria × outros distribuidores" — ajustes pendentes
Construído nesta sessão (06/10/2026) usando `distributorView` MANUFACTURING
(Fabricação, soma de todos os vendors da mesma marca) vs SOURCING (Origem, só
a própria conta) no `GET_VENDOR_SALES_REPORT`. Dúvidas do usuário esclarecidas
durante a sessão, registrar pra não perder o contexto:

- **Isso NÃO é "venda 1P × venda 3P" (marketplace)**. `GET_VENDOR_SALES_REPORT`
  é exclusivo de conta Vendor — não enxerga vendedores terceiros no marketplace
  de jeito nenhum. "Outros distribuidores" = outras contas Vendor cadastradas
  vendendo a mesma marca/fabricante (outro fornecedor direto pra Amazon), não
  revendedores do marketplace.
- **Testado e confirmado nesta sessão**: não há como buscar dados de 3P via
  API. Vendas de outros sellers são dado privado deles, a Amazon nunca expõe
  isso pra outro participante. Testei `get_item_offers` e
  `get_competitive_pricing_for_asins` (Product Pricing API) pra Blidshop — deu
  `Unauthorized` (permissão de Pricing não autorizada nessa integração Vendor).
  Pra ter visibilidade de ofertas/preços de terceiros (não vendas, só
  concorrência de Buy Box), precisaria autorizar a permissão "Pricing" no
  Seller Central da conta — configuração fora daqui. O card mais próximo que
  já temos hoje pra sinalizar concorrência é "Oferta em Destaque"
  (`transformar_destaque.py`), que mostra % de visualizações em que a Amazon/
  outro vendedor ganha o Buy Box — não é venda, mas é o proxy mais próximo que
  temos.
- **Ruído de medição**: contas sem nenhum outro distribuidor conhecido (ex.:
  Blidshop) ainda mostram uma diferença pequena entre Fabricação e Origem
  (Blidshop R$711, 0,4%; Rio Master R$394, 1%; WIWU R$641, 1,6%; Petiko R$30,
  1,5%) — isso é ruído de reconciliação entre os dois relatórios (pedidos
  separados à Amazon, podem ter cortes de dados ligeiramente diferentes), não
  um distribuidor real. Só Petclean (8%) e Jolitex (23%) têm diferença grande
  o suficiente pra ser provavelmente real.
  **Ação sugerida, ainda não aplicada**: só exibir "outros distribuidores" no
  card quando a diferença passar de um limite (ex.: 3-5%); abaixo disso,
  mostrar como "sem diferença relevante" pra não confundir contas que não têm
  outro distribuidor de verdade.
- **Texto do card a corrigir**: a label atual usa "outros distribuidores /
  market place", copiada do painel de referência do parceiro que o usuário
  mostrou — mas "market place" é enganoso dado o que a métrica realmente mede.
  Trocar por algo tipo "outros distribuidores/fornecedores Vendor da mesma
  marca".

## 5. Criação de listings novos (ASIN/SKU que ainda não existe) via API
Pergunta do usuário (06/10/2026): dá pra subir produto novo pelo mesmo
mecanismo usado hoje pra editar? Resposta: sim, tecnicamente — `putListingsItem`
("Creates a new or fully-updates an existing listings item") cria um listing
novo quando o SKU informado ainda não existe na conta, usando o mesmo endpoint
que já validamos hoje pra PATCH/PUT de edição.

Diferenças importantes em relação a editar um item existente (o que fizemos
hoje):
- Precisa enviar **todos** os atributos obrigatórios da categoria de uma vez
  (título, bullets, descrição, imagens, dimensões, EAN/GTIN ou isenção,
  preço/custo etc.) — não dá pra reaproveitar atributos já preenchidos, porque
  não existem ainda.
- Em conta Vendor (caso da Jolitex), a criação de ASIN novo pode passar por
  aprovação/triagem da Amazon antes de ficar visível — precisa confirmar esse
  comportamento especificamente (não testado ainda).
- Se o produto novo for variação de um já existente (cor/tamanho diferente do
  mesmo produto pai), entra a lógica de vínculo ao ASIN pai — mesma área que
  já deu problema hoje (atributo `size`/`color` inconsistente na família).

Ainda não implementado nem testado nesta sessão — é um fluxo novo (hoje só
mexemos em listings que já existiam). Desenhar com calma na próxima sessão:
provavelmente vale um teste piloto com 1 produto novo real antes de escalar,
igual fizemos hoje com a reclassificação de categoria.

## 6. Limite de 1.600 chamadas/dia — não confirmado como real
Investigado nesta sessão: não existe menção a um teto diário de 1.600 chamadas
na documentação oficial da SP-API (o rate limit documentado é por segundo,
ex: 5 req/s pra Listings Items API, sem teto diário). O usuário disse que o
número veio de um colega — combinamos de seguir só a documentação oficial daqui
pra frente, mas vale confirmar a origem do número caso reapareça.

## 7. Sessão de 06–10/10/2026 — conteúdo, variações e atributos (resumo + pendências)

### Feito (tudo aplicado via SP-API e conferido ao vivo)
- **Petiko**: 37/37 com título <75 + destaque; 3 itens reclassificados para PET_FEEDER;
  3 atributos de cor corrigidos (divergiam do título/model_name).
- **OZITP / KastKing**: 125 itens com título curto + destaque; variações criadas para
  106 linhas (4 famílias, tamanho em kg/m métrico) e 16 carretilhas/molinetes
  (7 famílias: mão direita/esquerda e tamanho).
- **OZITP / Mar Negro**: 12 bolsas/mochilas com conteúdo novo; 2 famílias de variação por cor.
- **New Pet**: 39 itens com conteúdo e atributos; 13 famílias de variação (32 filhos).
- **Jolitex**: diagnóstico ao vivo mostrou 953/1.173 já OK; 219/220 corrigidos (58 títulos
  + destaque, 161 bullets em caixa alta); 54 famílias de variação criadas (137 filhos).
- **Rio Master**: altura no título de 75 árvores de Natal (fonte: site + catálogo de Natal
  2025); atributos de árvore (galhos, luz, base, dimensões) em 75; medidas do catálogo de
  Natal (tamanho/dimensões/diâmetro) preenchidas em 1.707 anúncios.
- **Balboa (Ligga Sports)**: 446/446 com título <75 + destaque (base: catálogo "COLEÇÃO
  COMPLETA ATUALIZADO 06_05_2026"); 55 anúncios com bullets reescritos; 23 list_price
  convertidos para value_with_tax; 9 filhos com atributo de tamanho.

### Pendente
- **Pet Clean — eliminadores de odor em "Peitorais"** (7 ASINs: B099KTD8Q7, B091ZF5G3J,
  B08B2JVHRM, B089ZSH42B, B08B2GH7Z6, B099DK1G8Z, B08B2SF89F). Categoria travada (101168).
  Chamado pronto: `docs/chamados/petclean_2026-10-10_eliminadores_odor_categoria.md`.
  Após o suporte liberar: productType PET_SUPPLIES, categoria "Limpeza e Ambiente",
  nó "Eliminadores de Odor e Manchas", e conferir ao vivo.
- **Balboa — 45 anúncios do tipo genérico PRODUCT**: aceitaram título/destaque/bullets
  enviados como SHIRT/SWEATSHIRT/COAT, mas ainda aparecem como PRODUCT. Rechecar; se
  persistir, buscar outro caminho (ou chamado).
- **Balboa — destaques de moletom começando com "Juvenil, …"** (herdado do título antigo):
  limpeza cosmética opcional.
- **Jolitex — B0FD54CQFL (Faqueiro Baviera)**: EAN 07908891639640 duplicado com B0FFBKZX1G
  bloqueia qualquer PATCH; precisa de chamado com certificado GS1.
- **Jolitex — par U2.3006009** (pote "Lines" 600 ml × 1,4 L sem nome): confirmar se é o
  mesmo produto antes de criar variação.
- **Rio Master — toalhas SM3463/SM3464/SM3468**: catálogo traz "210m"/"240m" (erro de
  digitação); confirmar 2,10 m / 2,40 m e aplicar.
- **Rio Master — CX150G**: galhos divergentes (anúncio 547 × catálogo 574 × site 456).
- **Rio Master — 10 árvores sem altura em nenhuma fonte** (CX6981, CX1507, OMG0995,
  OMG0996, OMG0999, OMG1002, OMG1005, OMG1006, OMG1007, OMG1009).
- **Rio Master — dimensões das árvores grandes**: catálogo só tem altura; falta diâmetro.
- **Rio Master — remoção de "Ref. XXXX" em ~376 títulos**: rodada interrompida em
  sessão anterior; rechecar ao vivo quantos ainda têm "Ref.".
- **KastKing — destaque de B0BJVTRN3R (KLIBRDHM-150YBK40)**: falhou por erro transitório;
  reaplicar.
