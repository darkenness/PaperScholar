#!/bin/bash
# Configure container registry mirrors for China mainland servers

mkdir -p /etc/containers

cat > /etc/containers/registries.conf << 'EOF'
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
EOF

echo "Registry mirrors configured"
cat /etc/containers/registries.conf

# Now start PaperScholar
cd /opt/PaperScholar
docker compose up -d --build 2>&1
