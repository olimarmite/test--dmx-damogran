#!/bin/sh
# Lance Damogran sous Linux (et macOS). Aucune installation : utilise uv s'il est la, sinon python3.
cd "$(dirname "$0")" || exit 1

if command -v uv >/dev/null 2>&1; then
  exec uv run damogran.py "$@"
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
  exec python3 damogran.py "$@"
fi

echo "Il faut Python 3.8 ou plus (ou uv)."
echo "  Debian/Ubuntu : sudo apt install python3"
echo "  uv sans droits admin : curl -LsSf https://astral.sh/uv/install.sh | sh"
exit 1
