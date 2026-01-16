# 1단계: 빌드 스테이지
FROM node:20-alpine as build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# 아까 package.json에 정의한 build:docker 실행
RUN npm run build:docker

# 2단계: 실행 스테이지 (Nginx)
FROM nginx:stable-alpine

# 빌드 결과물 복사
COPY --from=build-stage /app/dist/ui/browser /usr/share/nginx/html
# Nginx 설정 파일 복사
COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]