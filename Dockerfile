# Usar imagem base com Python e Chrome
FROM python:3.11-slim

# Instalar dependências do sistema para Chrome e Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    curl \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O /etc/apt/keyrings/google-chrome.asc https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos de dependências
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Pré-cachear chromedriver durante o build (evita download em runtime)
RUN python -c "from webdriver_manager.chrome import ChromeDriverManager; ChromeDriverManager().install()"

# Copiar código do bot
COPY bot_discord.py .
COPY scrapers/ ./scrapers/

# Comando para executar o bot
CMD ["python", "bot_discord.py"]
