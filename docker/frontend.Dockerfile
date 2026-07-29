# =============================================================================
# ICD Writer — Frontend (React + Vite, served via nginx)
# Multi-stage build: Node builds the app, nginx serves static assets and
# proxies API requests to the backend container.
# Build context: ./frontend
# =============================================================================

# Stage 1: Build the React app
FROM node:22-alpine AS build

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Custom nginx config to proxy API requests to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
