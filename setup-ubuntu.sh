#!/bin/bash
# Day-News Setup Script for Ubuntu Server
# This script sets up the day-news project with Docker

set -e  # Exit on error

echo "🚀 Starting day-news setup..."

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  Not recommended to run as root. Use a regular user account."
fi

# Create project directory
PROJECT_DIR="$HOME/day-news"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "📦 Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed. Please log out and log back in for group changes to take effect."
else
    echo "✅ Docker is already installed"
fi

echo "📦 Checking Docker Compose installation..."
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose is already installed"
fi

echo "📝 Creating ven.env file..."
if [ ! -f "ven.env" ]; then
    cat > ven.env << 'EOF'
# News API (GNews or similar)
NEWS_API_KEY=your_gnews_api_key_here
NEWS_API_URL=https://gnews.io/api/v4/top-headlines
NEWS_LANG=en
NEWS_COUNTRY=us
NEWS_MAX=10

# Local LLM (Ollama)
OLLAMA_MODEL=gemma3:4b

# SMTP (optional for email delivery)
SMTP_HOST=
SMTP_PORT=465
SMTP_USER=
SMTP_PASS=
SMTP_SENDER=
SMTP_TO=
EOF
    chmod 600 ven.env  # Restrict permissions for security
    echo "✅ ven.env created (IMPORTANT: Fill in your credentials!)"
else
    echo "⚠️  ven.env already exists, skipping creation"
fi

echo "📦 Building Docker image..."
docker-compose build

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit ven.env with your credentials: nano ven.env"
echo "2. Run the digest: docker-compose run --rm day-news"
echo "3. For scheduled runs, set up cron: crontab -e"
echo ""
echo "To schedule daily at 8 AM, add:"
echo "0 8 * * * cd $PROJECT_DIR && docker-compose run --rm day-news >> /var/log/day-news.log 2>&1"
