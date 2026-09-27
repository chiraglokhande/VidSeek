#!/bin/bash
set -e

echo "Upgrading pip..."
python3 -m pip install --upgrade pip

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Deno..."
export DENO_INSTALL="$(pwd)/.deno"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL https://deno.land/x/install/install.sh | sh
elif command -v wget >/dev/null 2>&1; then
  wget -qO- https://deno.land/x/install/install.sh | sh
else
  # On some very stripped down images, we might need to use python to download
  python3 -c "import urllib.request, os; os.system(urllib.request.urlopen('https://deno.land/x/install/install.sh').read().decode('utf-8'))"
fi

export PATH="$DENO_INSTALL/bin:$PATH"

echo "Setting up bgutil-ytdlp-pot-provider..."
if [ ! -d "$(pwd)/bgutil-ytdlp-pot-provider" ]; then
  echo "Cloning bgutil-ytdlp-pot-provider repository..."
  git clone https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$(pwd)/bgutil-ytdlp-pot-provider"
else
  echo "bgutil-ytdlp-pot-provider already cloned."
fi

echo "Build script completed successfully!"
