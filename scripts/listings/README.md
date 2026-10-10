# scripts/listings — ferramentas de catálogo (todas as contas são Vendor)

Fluxo padrão para revisar/corrigir uma conta (rodar sempre da raiz do repositório):

1. **Buscar ao vivo** — `python3 scripts/listings/buscar.py <conta> /tmp/attrs.json`
   (retoma sozinho; use `--curto` para rodadas de 95 s ou rode em segundo plano).
2. **Diagnosticar** — `python3 scripts/listings/diagnosticar.py /tmp/attrs.json /tmp/diag.json`.
3. **Montar o plano** (script próprio da tarefa) no formato
   `[{"sku", "pt", "patches": [...]}]` — título e destaque no mesmo item.
4. **Preview em amostra** (≥1 por productType) —
   `python3 scripts/listings/aplicar.py <conta> plano.json --preview --curto SKU1 SKU2 ...`
5. **Aplicar** — `python3 scripts/listings/aplicar.py <conta> plano.json` (com retomada).
6. **Conferir ao vivo** uma amostra depois de aplicar.

Contas e credenciais: `contas.py`. Regras de conteúdo e armadilhas da API: `CLAUDE.md` na raiz.
