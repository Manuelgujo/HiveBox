#!/bin/bash

GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Cleaning up HiveBox cluster...${NC}"
kind delete cluster
echo -e "${GREEN}Cleanup complete!${NC}"