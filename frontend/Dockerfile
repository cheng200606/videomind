FROM node:22-alpine AS build
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /srv
COPY --from=build /srv .
EXPOSE 5173
# 课程项目本机演示用 vite preview，省掉一份 nginx 配置；端口与 compose/CORS 保持一致
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
