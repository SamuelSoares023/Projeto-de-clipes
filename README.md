# ClipLive AI

Ferramenta mobile-first para gerar cortes verticais (9:16) de lives automaticamente usando `yt-dlp`, `FFmpeg` e a API do Gemini.

## Como hospedar (Railway, Render ou Fly.io)

1. Extraia este arquivo `.zip` e suba o conteúdo da pasta `cliplive` para um repositório no GitHub.
2. Conecte o repositório no **Railway** ou **Render** (o `Dockerfile` será detectado automaticamente).
3. Adicione a variável de ambiente:
   - `GEMINI_API_KEY`: sua chave gerada no Google AI Studio.
4. Após o deploy, acesse o link gerado pelo celular.
