# Stage 1: Build the Angular app
FROM node:22-alpine AS build

WORKDIR /app

# Copy package.json and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code and build
COPY . .
RUN npm run build --configuration=production

# Stage 2: Serve the app with NGINX
FROM nginx:alpine

# Copy the built artifacts from Stage 1 to Nginx's web root
# Angular 17+ typically builds into dist/<project-name>/browser
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

# Copy custom NGINX configuration (optional, handles Angular routing)
RUN echo "server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files \$uri \$uri/ /index.html; \
    } \
}" > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
