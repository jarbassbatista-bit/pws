const express = require("express");
const app = express();
app.use(express.json());

// ============================================================
// CONFIGURAÇÕES — preencha com seus dados
// ============================================================
const CONFIG = {
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,   // console.anthropic.com
  ZAPI_INSTANCE:     "3F45B51C74DFF2AA7AA7FE743DE93AC5",   // z-api.io (opcional, ver README)
  ZAPI_TOKEN:        "32AB06403048DB069ED55973",
  SEU_NUMERO:        "5511992564805",           // seu número para notificações
  PIX_CHAVE:         "11992564805",
  MERCADO_PAGO_LINK: "https://mpago.la/2e62Exg",
};

// ============================================================
// INFORMAÇÕES DO NEGÓCIO
// ============================================================
const SISTEMA_PROMPT = `Você é o assistente virtual de vendas de uma loja de TV por aplicativo (IPTV/Streaming). Seu nome é Max. Seja simpático, objetivo e use linguagem informal mas profissional. Use emojis com moderação.

📺 PLANOS DISPONÍVEIS:

MENSAL:
- 1 tela: R$ 35,00
- 2 telas: R$ 45,00
- 3 telas: R$ 60,00

TRIMESTRAL (economize pagando menos por mês):
- 1 tela: R$ 90,00
- 2 telas: R$ 115,00
- 3 telas: R$ 130,00

SEMESTRAL:
- 1 tela: R$ 150,00
- 2 telas: R$ 180,00
- 3 telas: R$ 210,00

ANUAL (melhor custo-benefício):
- 1 tela: R$ 250,00
- 2 telas: R$ 280,00
- 3 telas: R$ 310,00

📡 CANAIS INCLUSOS EM TODOS OS PLANOS:
Canais abertos, fechados (Globo, SBT, Record, Band, CNN, GNT, Discovery, National Geographic), infantis (Disney, Cartoon, Nickelodeon), esportivos (ESPN, SporTV, Combate), notícias, filmes, séries e muito mais — mais de 10.000 canais ao vivo + VOD.

💳 FORMAS DE PAGAMENTO:
- PIX (ativação imediata)
- Link do Mercado Pago (cartão de crédito/débito)

⚡ COMO FUNCIONA:
1. Cliente escolhe o plano
2. Realiza o pagamento
3. Envia o comprovante aqui no WhatsApp
4. Ativação IMEDIATA — acesso enviado aqui mesmo pelo WhatsApp

🛠️ SUPORTE PÓS-VENDA:
- Atendimento 100% pelo WhatsApp
- 8 servidores disponíveis para mais agilidade
- Equipe técnica pronta para resolver qualquer problema

INSTRUÇÕES DE COMPORTAMENTO:
- Quando o cliente perguntar sobre planos, mostre todos de forma organizada
- Sempre destaque que a ativação é imediata após o comprovante
- Quando o cliente quiser comprar, pergunte quantas telas precisa e qual período prefere
- Após definir o plano, informe o valor e as formas de pagamento
- Se o cliente pedir o PIX, informe a chave: ${CONFIG.PIX_CHAVE}
- Se preferir cartão, envie o link: ${CONFIG.MERCADO_PAGO_LINK}
- Para dúvidas técnicas ou suporte, informe que nossa equipe vai atender em instantes
- NUNCA invente informações que não estão neste prompt
- Se não souber responder algo, diga que vai verificar e acionar o suporte humano`;

// ============================================================
// MEMÓRIA DE CONVERSAS (em memória, reinicia com o servidor)
// ============================================================
const conversas = new Map();

function getHistorico(numero) {
  if (!conversas.has(numero)) conversas.set(numero, []);
  return conversas.get(numero);
}

function addMensagem(numero, role, content) {
  const hist = getHistorico(numero);
  hist.push({ role, content });
  // Mantém só as últimas 20 mensagens para não estourar contexto
  if (hist.length > 20) hist.splice(0, hist.length - 20);
}

// ============================================================
// CHAMAR CLAUDE AI
// ============================================================
async function chamarClaude(numero, mensagemUsuario) {
  addMensagem(numero, "user", mensagemUsuario);
  const historico = getHistorico(numero);

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": CONFIG.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      system: SISTEMA_PROMPT,
      messages: historico,
    }),
  });

  const data = await response.json();
  const resposta = data.content?.[0]?.text || "Desculpe, tive um problema. Tente novamente em instantes! 🙏";
  addMensagem(numero, "assistant", resposta);
  return resposta;
}

// ============================================================
// ENVIAR MENSAGEM VIA Z-API
// ============================================================
async function enviarMensagem(numero, texto) {
  const url = `https://api.z-api.io/instances/${CONFIG.ZAPI_INSTANCE}/token/${CONFIG.ZAPI_TOKEN}/send-text`;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: numero, message: texto }),
  });
}

// ============================================================
// WEBHOOK — recebe mensagens do WhatsApp
// ============================================================
app.post("/webhook", async (req, res) => {
  try {
    const body = req.body;

    // Ignora mensagens enviadas pelo próprio bot
    if (body.fromMe) return res.sendStatus(200);

    const numero = body.phone || body.from;
    const texto  = body.text?.message || body.body || "";

    if (!numero || !texto) return res.sendStatus(200);

    console.log(`📩 [${numero}]: ${texto}`);

    // Gera resposta com Claude
    const resposta = await chamarClaude(numero, texto);
    console.log(`🤖 Resposta: ${resposta}`);

    // Envia pelo WhatsApp
    await enviarMensagem(numero, resposta);

    res.sendStatus(200);
  } catch (err) {
    console.error("Erro no webhook:", err);
    res.sendStatus(500);
  }
});

// ============================================================
// ROTA DE TESTE — acesse no navegador para ver se está online
// ============================================================
app.get("/", (req, res) => {
  res.send("✅ Bot de streaming online e funcionando!");
});

// ============================================================
// INICIA O SERVIDOR
// ============================================================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 Bot rodando na porta ${PORT}`);
  console.log(`📌 Configure o webhook da Z-API para: SEU_DOMINIO/webhook`);
});
