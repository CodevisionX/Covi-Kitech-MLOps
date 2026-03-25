#!/bin/bash

# MLOps Stack Deployment Script
# Optimized for Unified NGC-based Architecture (Supporting Turing to Blackwell)

# Stop the script on any error
set -e

echo "------------------------------------------------------"
echo "Initializing MLOps Stack Deployment..."
echo "Target: Unified NVIDIA NGC-based Environment"
echo "------------------------------------------------------"

# 1. Pull the latest images from the Container Registry
echo "[1/3] Updating all images (including tools and job profiles) from GHCR..."
docker compose --profile tools --profile job pull

# 2. Start the services in detached mode
echo "[2/3] Starting all services in the background..."
docker compose up -d

# 3. Clean up dangling images to save disk space
echo "[3/3] Cleaning up unused resources..."
docker image prune -f

echo "------------------------------------------------------"
echo "Deployment completed successfully."
echo ""
echo "Service Access Points:"
echo "- Backend API:  http://localhost:18000"
echo "- Jupyter Lab:  http://localhost:8888"
echo "- MLflow:       http://localhost:15000"
echo "- Frontend UI:  http://localhost:18080"
echo "------------------------------------------------------"
echo "To monitor service logs, use: docker compose logs -f"
echo "------------------------------------------------------"