#!/bin/bash
# Installation des dépendances système + venv Python dédié pour rainbirdtbosbt.
#
# Bonne pratique Jeedom : environnement Python isolé par plugin pour éviter
# tout conflit de version (bleak, etc.) avec d'autres plugins ou avec le
# Python système du Pi. Le venv vit dans resources/venv et le plugin pointe
# par défaut sur resources/venv/bin/python3.
#
# Lancé par Jeedom lors de l'installation/mise à jour du plugin.

set -e

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PLUGIN_DIR}/resources/venv"

echo "=== rainbirdtbosbt : installation des dépendances ==="

# 1. Paquets système (glib2.0, bluez) requis par bleak sur Linux.
if command -v apt-get >/dev/null 2>&1; then
    echo "-> apt-get update / install"
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip python3-dbus python3-gi \
        libglib2.0-dev bluez
elif command -v dnf >/dev/null 2>&1; then
    echo "-> dnf install"
    dnf install -y python3 python3-venv python3-pip python3-dbus python3-gobject \
        glib2-devel bluez
elif command -v apk >/dev/null 2>&1; then
    echo "-> apk add"
    apk add --no-cache python3 py3-venv py3-pip python3-dbus py3-gobject3 \
        glib-dev bluez
else
    echo "! Gestionnaire de paquets inconnu — venv créé avec le python3 système."
fi

# 2. Création du venv dédié au plugin (isolé du système et des autres plugins).
echo "-> création du venv : ${VENV_DIR}"
python3 -m venv "${VENV_DIR}" 2>/dev/null \
    || { echo "! venv indisponible, fallback pip système"; }

VENV_PY="${VENV_DIR}/bin/python3"
if [ -x "${VENV_PY}" ]; then
    echo "-> installation de bleak dans le venv"
    # --upgrade pip pour la gestion récente des wheels, puis bleak.
    "${VENV_PY}" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "${VENV_PY}" -m pip install "bleak==0.21.1" \
        || "${VENV_PY}" -m pip install bleak
    echo "=== Venv prêt : ${VENV_PY} ==="
else
    # Fallback : pip système si le module venv manque.
    echo "-> fallback : pip système"
    pip3 install --break-system-packages "bleak==0.21.1" 2>/dev/null \
        || pip3 install "bleak==0.21.1" \
        || pip3 install bleak
fi

echo "=== Dépendances installées ==="
