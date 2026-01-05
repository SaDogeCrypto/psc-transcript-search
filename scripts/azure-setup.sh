#!/bin/bash
# CanaryScope Azure Infrastructure Setup
# Run this once to create all Azure resources

set -e

# Configuration
RESOURCE_GROUP="canaryscope-rg"
LOCATION="eastus"
ACR_NAME="canaryscopeacr"
POSTGRES_SERVER="canaryscope-db"
POSTGRES_DB="canaryscope"
POSTGRES_USER="canaryscope_admin"
CONTAINER_ENV="canaryscope-env"
BACKEND_APP="canaryscope-backend"
FRONTEND_APP="canaryscope-frontend"
ACS_NAME="canaryscope-acs"
EMAIL_DOMAIN="canaryscope"

echo "Creating CanaryScope Azure infrastructure..."

# Create resource group
echo "Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Azure Container Registry
echo "Creating Container Registry..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query "username" -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

echo "ACR Username: $ACR_USERNAME"
echo "ACR Password: $ACR_PASSWORD"

# Create PostgreSQL Flexible Server with pgvector
echo "Creating PostgreSQL Flexible Server..."
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --location $LOCATION \
  --admin-user $POSTGRES_USER \
  --admin-password "${POSTGRES_PASSWORD:-$(openssl rand -base64 24)}" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --yes

# Enable pgvector extension
echo "Enabling pgvector extension..."
az postgres flexible-server parameter set \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --name azure.extensions \
  --value vector

# Create database
echo "Creating database..."
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --database-name $POSTGRES_DB

# Allow Azure services to access PostgreSQL
echo "Configuring firewall..."
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Create Container Apps Environment
echo "Creating Container Apps Environment..."
az containerapp env create \
  --name $CONTAINER_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Create Azure Communication Services
echo "Creating Azure Communication Services..."
az communication create \
  --name $ACS_NAME \
  --resource-group $RESOURCE_GROUP \
  --location Global \
  --data-location UnitedStates

# Get ACS connection string
ACS_CONNECTION_STRING=$(az communication list-key \
  --name $ACS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "primaryConnectionString" -o tsv)

echo ""
echo "Azure Communication Services created!"
echo "Connection String: $ACS_CONNECTION_STRING"
echo ""
echo "NOTE: To enable email, you need to:"
echo "1. Go to Azure Portal > Communication Services > $ACS_NAME"
echo "2. Click 'Try Email' or 'Domains' under Email"
echo "3. Add an Azure Managed Domain or custom domain"
echo "4. Note the sender address (e.g., DoNotReply@<domain>.azurecomm.net)"
echo ""

# Get database connection string
POSTGRES_HOST="${POSTGRES_SERVER}.postgres.database.azure.com"
DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}?sslmode=require"

echo ""
echo "=========================================="
echo "Azure infrastructure created successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add these secrets to GitHub repository:"
echo "   - ACR_USERNAME: $ACR_USERNAME"
echo "   - ACR_PASSWORD: $ACR_PASSWORD"
echo "   - AZURE_CREDENTIALS: (run 'az ad sp create-for-rbac' for service principal)"
echo ""
echo "2. Create Container Apps:"
echo "   az containerapp create --name $BACKEND_APP --resource-group $RESOURCE_GROUP --environment $CONTAINER_ENV --image $ACR_NAME.azurecr.io/canaryscope-backend:latest --target-port 8000 --ingress external --registry-server $ACR_NAME.azurecr.io"
echo ""
echo "3. Set environment variables in Container Apps:"
echo "   DATABASE_URL: $DATABASE_URL"
echo "   OPENAI_API_KEY: (your key)"
echo "   AZURE_COMMUNICATION_CONNECTION_STRING: $ACS_CONNECTION_STRING"
echo "   AZURE_EMAIL_SENDER: DoNotReply@<your-domain>.azurecomm.net"
echo ""
