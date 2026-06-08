# 🤖 Bot de Vendas de Streaming — WhatsApp

## Como colocar no ar (passo a passo)

---

### PASSO 1 — Criar conta na Z-API (gratuito por 7 dias)
1. Acesse: https://z-api.io
2. Clique em "Começar grátis"
3. Crie uma instância
4. Escaneie o QR Code com seu WhatsApp Business
5. Anote a **Instance ID** e o **Token**

---

### PASSO 2 — Pegar chave da Anthropic (Claude AI)
1. Acesse: https://console.anthropic.com
2. Crie sua conta (recebe créditos gratuitos)
3. Vá em "API Keys" → "Create Key"
4. Copie a chave (começa com sk-ant-...)

---

### PASSO 3 — Subir no Render.com (hospedagem gratuita)
1. Acesse: https://render.com e crie conta com o GitHub
2. No GitHub, crie um repositório novo e envie estes arquivos
3. No Render: "New" → "Web Service" → conecte seu repositório
4. Configure:
   - Build Command: npm install
   - Start Command: node index.js
5. Clique em "Deploy"
6. Anote a URL gerada (ex: https://meu-bot.onrender.com)

---

### PASSO 4 — Preencher as configurações no index.js
Abra o arquivo index.js e preencha o bloco CONFIG:

```js
const CONFIG = {
  ANTHROPIC_API_KEY: "sk-ant-SUA_CHAVE_AQUI",
  ZAPI_INSTANCE:     "SUA_INSTANCE_ID",
  ZAPI_TOKEN:        "SEU_TOKEN",
  SEU_NUMERO:        "5511999999999",
  PIX_CHAVE:         "sua@chave.pix",
  MERCADO_PAGO_LINK: "https://link.mercadopago.com.br/...",
};
```

---

### PASSO 5 — Configurar o Webhook na Z-API
1. Acesse o painel da Z-API
2. Vá em "Webhooks" da sua instância
3. Cole sua URL do Render + /webhook
   Exemplo: https://meu-bot.onrender.com/webhook
4. Salve

✅ Pronto! Seu bot já vai responder automaticamente no WhatsApp.

---

## Testando
- Acesse sua URL no navegador — deve aparecer: "✅ Bot de streaming online e funcionando!"
- Mande uma mensagem no WhatsApp conectado
- O bot vai responder automaticamente

## Dúvidas comuns
- **Bot não responde:** verifique se o webhook está salvo na Z-API corretamente
- **Erro de API:** confirme que a chave da Anthropic está correta no CONFIG
- **WhatsApp desconectou:** escaneie o QR Code novamente na Z-API
