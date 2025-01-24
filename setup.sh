#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting HiveBox setup...${NC}"

# Function to check if required tools are installed
check_tool() {
    local tool=$1
    local install_instructions=$2
    
    if ! command -v $tool &> /dev/null; then
        echo -e "${RED}$tool is required but not installed.${NC}"
        echo -e "${YELLOW}Installation instructions:${NC}"
        echo -e "$install_instructions"
        exit 1
    fi
}

# Check for required tools first
check_tool "docker" "Please visit https://docs.docker.com/get-docker/ for installation instructions."

check_tool "kubectl" "Please visit https://kubernetes.io/docs/tasks/tools/ for installation instructions."

check_tool "kind" "Install using: 'go install sigs.k8s.io/kind@latest' or visit https://kind.sigs.k8s.io/docs/user/quick-start/"

check_tool "helm" "Install using one of these methods:
- Linux: curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
- macOS: brew install helm
- Windows: choco install kubernetes-helm"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Check if Kind cluster exists and delete it if it does
if kind get clusters | grep -q "^kind$"; then
    echo -e "${YELLOW}Existing Kind cluster found. Deleting it...${NC}"
    kind delete cluster
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

# Wait for ingress-nginx namespace to be created
echo -e "${YELLOW}Waiting for ingress-nginx namespace to be created...${NC}"
while ! kubectl get namespace ingress-nginx >/dev/null 2>&1; do
    sleep 2
done

# Patch ingress-nginx for resource constraints
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

# Apply base Kustomize configuration (including namespaces)
echo -e "${GREEN}Applying base Kustomize configuration...${NC}"
kubectl apply -k kustomize/base || {
    echo -e "${RED}Failed to apply base configuration${NC}"
    exit 1
}
# Clean up any existing PVCs
echo -e "${GREEN}Cleaning up existing PVCs...${NC}"
kubectl delete pvc --all -n hivebox-dev 2>/dev/null || true
sleep 2

# Apply development overlay configuration (this will create the namespace and PVCs)
echo -e "${GREEN}Applying development overlay configuration...${NC}"
kubectl apply -k kustomize/overlays/development || {
    echo -e "${RED}Failed to apply development overlay${NC}"
    exit 1
}

# Wait for PVCs to be created
echo -e "${YELLOW}Waiting for PVCs to be created...${NC}"
sleep 5

# Install Helm chart
echo -e "${GREEN}Installing Helm chart...${NC}"
helm install hivebox helm/hivebox -n hivebox-dev

# Wait for HiveBox deployment to be ready
echo -e "${YELLOW}Waiting for HiveBox deployment to be ready...${NC}"
wait_for_pod_ready "hivebox-dev" "app.kubernetes.io/name=hivebox"

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