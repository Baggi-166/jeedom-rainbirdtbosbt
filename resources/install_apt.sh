#!/bin/bash
# Installation des dépendances système pour rainbirdtbosbt.
# Dépendance Python unique : bleak (Bluetooth Low Energy).
# Lancé par Jeedom lors de l'installation/mise à jour du plugin.

set -e

echo "=== rainbirdtbosbt : installation des dépendances ==="

# 1. Paquets système (glib2.0, bluez) requis par bleak sur Linux.
if command -v apt-get >/dev/null 2>&1; then
    echo "-> apt-get update / install"
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-dbus python3-gi \
        libglib2.0-dev bluez
elif command -v dnf >/dev/null 2>&1; then
    echo "-> dnf install"
    dnf install -y python3 python3-pip python3-dbus python3-gobject \
        glib2-devel bluez
elif command -v apk >/dev/null 2>&1; then
    echo "-> apk add"
    apk add --no-cache python3 py3-pip python3-dbus py3-gobject3 \
        glib-dev bluez
else
    echo "! Gestionnaire de paquets inconnu — installation de bleak via pip uniquement."
fi

# 2. Bibliothèque Python bleak (version 0.21.1 pour compat Python 3.9).
echo "-> pip install bleak"
pip3 install --break-system-packages "bleak==0.21.1" 2>/dev/null \
    || pip3 install "bleak==0.21.1" \
    || pip3 install bleak

echo "=== Dépendances installées ==="
