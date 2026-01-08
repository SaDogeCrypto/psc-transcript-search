#!/bin/bash
# Deploy Florida API to Azure Container Apps

set -e

# Configuration
RESOURCE_GROUP="canaryscope-rg"
LOCATION="westus2"
ACR_NAME="canaryscopeacr"
APP_NAME="florida-api"
IMAGE_NAME="florida-api"

echo "=== Deploying Florida API to Azure ==="

# Step 1: Build and push Docker image
echo "Building Docker image..."
cd /home/ronan/psc-transcript-search
docker build -f packages/florida/Dockerfile -t $IMAGE_NAME .

# Tag for ACR
echo "Tagging image for ACR..."
docker tag $IMAGE_NAME $ACR_NAME.azurecr.io/$IMAGE_NAME:latest

# Login to ACR
echo "Logging in to ACR..."
az acr login --name $ACR_NAME

# Push image
echo "Pushing image to ACR..."
docker push $ACR_NAME.azurecr.io/$IMAGE_NAME:latest

# Step 2: Create or update Container App
echo "Deploying to Container Apps..."
az containerapp create \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --environment canaryscope-env \
    --image $ACR_NAME.azurecr.io/$IMAGE_NAME:latest \
    --target-port 8001 \
    --ingress external \
    --registry-server $ACR_NAME.azurecr.io \
    --env-vars \
        FL_DATABASE_URL="postgresql://csadmin:6IyN%2A%40%2AbJ%23SmS2dCCYGJiL7Z@canaryscope-florida.postgres.database.azure.com/florida?sslmode=require" \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 0.5 \
    --memory 1.0Gi

# Get the URL
echo "=== Deployment Complete ==="
az containerapp show --name $APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv
