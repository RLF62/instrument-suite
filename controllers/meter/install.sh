#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ "$#" -gt 0 ]; then
  exec python3 standalone_install.py "$@"
fi
echo 'HP 34401A installation'
echo '1) Meter only (no HP supply application required)'
echo '2) Add meter to an existing HP supply installation'
read -r -p 'Choose 1 or 2: ' mode
if [ "$mode" = 2 ]; then
  read -r -p 'Installed tools [meter,supply] (add ,scope only if installed): ' instruments
  instruments=${instruments:-meter,supply}
  /home/pi/hp6033a/venv/bin/python install.py --check --instruments "$instruments"
  read -r -p 'Apply the checked add-on update? [y/N] ' answer
  [ "$answer" = y ] && exec /home/pi/hp6033a/venv/bin/python install.py --apply --instruments "$instruments"
  exit 0
fi
[ "$mode" = 1 ] || { echo 'Invalid selection'; exit 1; }
echo 'Meter-only mode provides HTTP access on your trusted LAN, without login or encryption.'
echo 'No scope or supply links are shown. Hardware starts disabled.'
python3 standalone_install.py --check --listen 0.0.0.0
read -r -p 'Install meter-only mode on this trusted LAN? [y/N] ' answer
[ "$answer" = y ] || exit 0
sudo -v
exec python3 standalone_install.py --apply --listen 0.0.0.0
