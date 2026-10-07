# ReliefTrace dashboard (React/Vite), served as a static build via nginx.
# Build:  docker build -t relieftrace-frontend --build-arg VITE_API_BASE=http://localhost:8000/api .
FROM node:22-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_BASE=http://localhost:8000/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
