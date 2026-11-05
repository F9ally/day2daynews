
#!/bin/bash
# Day-News Docker Setup Script for Ubuntu
# This script automates the complete setup process
# Run with: bash setup-docker.sh

set -e  # Exit on any error

echo "=========================================="
echo "  Day-News Docker Setup Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PROJECT_DIR="$HOME/day-news"

# Step 1: Install Docker Compose
echo -e "${YELLOW}[1/6] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-Linux-x86_64 -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✓ Docker Compose already installed$(docker-compose --version)${NC}"
fi

# Step 2: Navigate to project
echo -e "${YELLOW}[2/6] Navigating to project directory...${NC}"
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}✗ Project directory not found at $PROJECT_DIR${NC}"
    echo "Please ensure day-news is cloned to ~/day-news"
    exit 1
fi
cd "$PROJECT_DIR"
echo -e "${GREEN}✓ In directory: $(pwd)${NC}"

# Step 3: Create Dockerfile
echo -e "${YELLOW}[3/6] Creating Dockerfile...${NC}"
cat > Dockerfile << 'DOCKERFILE_EOF'
FROM python:3.11-slim

# Install system dependencies (ffmpeg required for pydub)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create output directory for digests
RUN mkdir -p out

# Set proper permissions
RUN chmod +x scripts/fetch_and_publish_digest.py

# Run the script
CMD ["python", "scripts/fetch_and_publish_digest.py"]
DOCKERFILE_EOF
echo -e "${GREEN}✓ Dockerfile created${NC}"

# Step 4: Create docker-compose.yml
echo -e "${YELLOW}[4/6] Creating docker-compose.yml...${NC}"
cat > docker-compose.yml << 'COMPOSE_EOF'
services:
  day-news:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: day-news-digest
    env_file:
      - ven.env
    environment:
      - OLLAMA_HOST=http://127.0.0.1:11434
    volumes:
      - ./out:/app/out
    network_mode: host
    restart: "no"
COMPOSE_EOF
echo -e "${GREEN}✓ docker-compose.yml created${NC}"

# Step 5: Create .dockerignore
echo -e "${YELLOW}[5/6] Creating .dockerignore...${NC}"
cat > .dockerignore << 'IGNORE_EOF'
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.git
.gitignore
.env
ven.env
out/
.vscode
node_modules
.DS_Store
*.log
IGNORE_EOF
echo -e "${GREEN}✓ .dockerignore created${NC}"

# Step 6: Setup ven.env
echo -e "${YELLOW}[6/6] Setting up environment file...${NC}"
if [ ! -f "ven.env" ]; then
    cp ven.env.example ven.env
    chmod 600 ven.env
    echo -e "${GREEN}✓ ven.env created from template${NC}"
    echo ""
    echo -e "${YELLOW}IMPORTANT: Edit ven.env with your credentials!${NC}"
    echo "Run: nano ven.env"
    echo ""
    echo "Required credentials:"
    echo "  - NEWS_API_KEY: Your GNews API key"
    echo ""
else
    echo -e "${GREEN}✓ ven.env already exists${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit credentials: nano ven.env"
echo "2. Build Docker image: docker-compose build"
echo "3. Test first run: docker-compose run --rm day-news"
echo ""
echo "For automatic daily runs, set up cron:"
echo "  crontab -e"
echo ""
echo "Add this line (runs daily at 8 AM):"
echo "  0 8 * * * cd $PROJECT_DIR && docker-compose run --rm day-news >> /var/log/day-news.log 2>&1"
echo ""
