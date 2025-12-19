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
# 빌드 결과물 경로가 dist/프로젝트명/browser 일 수 있으니 확인 필요
COPY --from=build-stage /app/dist/ui/browser /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]