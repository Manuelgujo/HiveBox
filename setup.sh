#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting HiveBox setup...${NC}"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Create KIND cluster
echo -e "${GREEN}Creating KIND cluster...${NC}"
kind create cluster --config kind-config.yaml

# Install Ingress NGINX
echo -e "${GREEN}Installing NGINX Ingress Controller...${NC}"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/kind/deploy.yaml

# Function to wait for pod readiness
wait_for_pod_ready() {
    namespace=$1
    label=$2
    echo -e "${YELLOW}Waiting for pod with label $label in namespace $namespace...${NC}"
    
    while true; do
        if kubectl get pods -n "$namespace" -l "$label" -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}' | grep -q "True"; then
            echo -e "${GREEN}Pod is ready!${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
    done
}

# First wait for the namespace to be created
echo -e "${YELLOW}Waiting for ingress-nginx namespace to be created...${NC}"
while ! kubectl get namespace ingress-nginx >/dev/null 2>&1; do
    sleep 2
done

# Patch ingress-nginx immediately after namespace creation
echo -e "${GREEN}Patching NGINX Ingress Controller resources...${NC}"
kubectl patch deployment ingress-nginx-controller -n ingress-nginx --type='json' -p='[
  {
    "op": "replace",
    "path": "/spec/template/spec/containers/0/resources",
    "value": {
      "requests": {
        "cpu": "50m",
        "memory": "90Mi"
      },
      "limits": {
        "cpu": "200m",
        "memory": "180Mi"
      }
    }
  }
]'

# Wait for ingress controller to be ready
echo -e "${YELLOW}Waiting for ingress controller to be ready...${NC}"
wait_for_pod_ready "ingress-nginx" "app.kubernetes.io/component=controller"

# Build and load Docker image
echo -e "${GREEN}Building and loading Docker image...${NC}"
docker build -t hivebox:latest .
kind load docker-image hivebox:latest

# Apply Kubernetes manifests in order
echo -e "${GREEN}Applying Kubernetes manifests...${NC}"
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Wait for deployment to be ready
echo -e "${YELLOW}Waiting for HiveBox deployment to be ready...${NC}"
wait_for_pod_ready "default" "app=hivebox"

# Now apply ingress
echo -e "${GREEN}Creating ingress...${NC}"
kubectl apply -f k8s/ingress.yaml

# Final wait to ensure everything is ready
echo -e "${YELLOW}Waiting for final setup...${NC}"
sleep 10

# Test endpoints
echo -e "${GREEN}Setup complete! Testing endpoints...${NC}"
echo -e "${GREEN}Version endpoint:${NC}"
curl -s localhost/version || echo -e "${RED}Failed to reach version endpoint${NC}"
echo -e "\n${GREEN}Temperature endpoint:${NC}"
curl -s localhost/temperature || echo -e "${RED}Failed to reach temperature endpoint${NC}"

# Show pod status
echo -e "\n${GREEN}Current pod status:${NC}"
kubectl get pods -A

echo -e "\n${GREEN}HiveBox setup completed!${NC}"