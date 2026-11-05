FROM node:22-alpine AS build
WORKDIR /srv
COPY package.json ./
# 无 lockfile 时的安装入口；本地跑通后请提交 package-lock.json 锁版本
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /srv
COPY --from=build /srv .
EXPOSE 4173
# 课程项目本机演示用 vite preview，省掉一份 nginx 配置
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0"]
