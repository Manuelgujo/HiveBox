#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting HiveBox cleanup...${NC}"

# Uninstall Helm release
echo -e "${GREEN}Uninstalling Helm release...${NC}"
helm uninstall hivebox -n hivebox-dev 2>/dev/null || true

# Remove namespaces and their contents
echo -e "${GREEN}Removing namespaces...${NC}"
kubectl delete namespace hivebox-dev --timeout=60s 2>/dev/null || true
kubectl delete namespace hivebox-prod --timeout=60s 2>/dev/null || true

# Delete KIND cluster
echo -e "${GREEN}Deleting KIND cluster...${NC}"
kind delete cluster

echo -e "${GREEN}Cleanup complete!${NC}"