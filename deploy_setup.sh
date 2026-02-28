#!/bin/bash
set -e

cd /opt/PaperScholar/backend

# Generate secrets
SECRET=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
API_ENC=$(openssl rand -hex 16)

# Write .env
cat > .env << EOF
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
CORS_ORIGINS=["http://39.106.47.92:3000","http://39.106.47.92"]
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=20
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@paperscholar.local
EOF

echo "Backend .env created"

# Frontend env
cd /opt/PaperScholar/frontend
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://39.106.47.92:8000
EOF

echo "Frontend .env.local created"

# Start services
cd /opt/PaperScholar
docker compose up -d --build 2>&1

echo "Deploy complete!"
