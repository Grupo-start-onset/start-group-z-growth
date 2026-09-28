// Cloudflare Pages Function -- API de anotacoes manuais na aba "Pedidos"
// (valor faturado + status, por pedido). Nao mexe nos dados capturados da
// SP-API; e um complemento manual, guardado a parte no KV.
//
// Rota: /api/pedidos-anotacoes
//   GET  -> devolve todas as anotacoes: { "<conta>|<po>": {valorFaturado, status, atualizadoEm} }
//   POST -> grava/atualiza uma anotacao. Corpo: { conta, po, valorFaturado, status }
//
// Protecao: este endpoint fica atras do mesmo Cloudflare Access do resto do
// site (a aplicacao Access cobre o dominio inteiro) -- so chega aqui quem
// ja fez login. Nao ha autenticacao propria alem dessa.
//
// Armazenamento: um unico JSON no KV (chave fixa "anotacoes"). Volume baixo
// (algumas centenas de pedidos), entao nao precisa de nada mais sofisticado;
// ultima escrita vence em caso de edicao simultanea rara.
//
// Binding necessario no projeto Cloudflare Pages (Settings > Functions >
// KV namespace bindings): variavel PEDIDOS_KV -> namespace
// "start-group-z-growth-pedidos-anotacoes".

const CHAVE_KV = 'anotacoes';

export async function onRequestGet({ env }) {
  const dados = await lerTudo(env);
  return json(dados);
}

export async function onRequestPost({ request, env }) {
  let corpo;
  try {
    corpo = await request.json();
  } catch {
    return json({ erro: 'JSON invalido' }, 400);
  }
  const { conta, po } = corpo;
  if (!conta || !po) return json({ erro: 'conta e po sao obrigatorios' }, 400);

  const valorFaturado = corpo.valorFaturado === '' || corpo.valorFaturado == null
    ? null : Number(corpo.valorFaturado);
  const status = typeof corpo.status === 'string' ? corpo.status.slice(0, 200) : '';

  const dados = await lerTudo(env);
  const chave = `${conta}|${po}`;
  dados[chave] = { valorFaturado, status, atualizadoEm: new Date().toISOString() };
  await env.PEDIDOS_KV.put(CHAVE_KV, JSON.stringify(dados));
  return json(dados[chave]);
}

async function lerTudo(env) {
  const bruto = await env.PEDIDOS_KV.get(CHAVE_KV);
  if (!bruto) return {};
  try { return JSON.parse(bruto); } catch { return {}; }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}
