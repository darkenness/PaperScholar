#!/bin/bash
set -e

PROJECT_DIR=/root/paperscholar
SERVER_IP=39.106.47.92

echo "=== 1. Configuring container registry mirrors ==="
cat > /etc/containers/registries.conf << 'REGEOF'
unqualified-search-registries = ["docker.io"]

[[registry]]
prefix = "docker.io"
location = "docker.io"

[[registry.mirror]]
location = "docker.1ms.run"

[[registry.mirror]]
location = "docker.xuanyuan.me"

[[registry.mirror]]
location = "hub.rat.dev"
REGEOF
echo "Mirrors configured:"
cat /etc/containers/registries.conf

echo ""
echo "=== 2. Creating backend .env ==="
SECRET=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
API_ENC=$(openssl rand -hex 16)

cat > $PROJECT_DIR/backend/.env << ENVEOF
APP_NAME=PaperScholar
APP_ENV=production
DEBUG=false
SECRET_KEY=$SECRET
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+asyncpg://paperscholar:paperscholar@db:5432/paperscholar
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
API_KEY_ENCRYPTION_KEY=$API_ENC
CORS_ORIGINS=["http://${SERVER_IP}:3000","http://${SERVER_IP}"]
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=20
ENVEOF
echo "Backend .env created"

echo ""
echo "=== 3. Creating frontend .env.local ==="
cat > $PROJECT_DIR/frontend/.env.local << FEOF
NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000
FEOF
echo "Frontend .env.local created"

echo ""
echo "=== 4. Opening firewall ports ==="
firewall-cmd --permanent --add-port=3000/tcp 2>/dev/null || true
firewall-cmd --permanent --add-port=8000/tcp 2>/dev/null || true
firewall-cmd --reload 2>/dev/null || true
echo "Firewall configured"

echo ""
echo "=== 5. Building and starting services ==="
cd $PROJECT_DIR
docker compose up -d --build 2>&1

echo ""
echo "=== Setup complete! ==="
echo "Frontend: http://${SERVER_IP}:3000"
echo "Backend:  http://${SERVER_IP}:8000"
