FROM mcr.microsoft.com/playwright:v1.64.1-noble
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund && useradd --create-home --uid 10101 agent
COPY server.js ./
USER agent
ENV NODE_ENV=production
ENV HOME=/home/agent
ENV XDG_CONFIG_HOME=/tmp/.chromium
ENV XDG_CACHE_HOME=/tmp/.chromium
EXPOSE 8822
CMD ["node", "server.js"]
