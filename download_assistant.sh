#!/usr/bin/env bash

# Avbryt direkt om något kommando misslyckas
set -e

DOWNLOAD_DIR="Nedladdningar"
API_URL="https://github.com"

echo "=================================================="
echo "      UNIVERSELL NEDLADDNINGSASSISTENT"
echo "=================================================="
echo

# 1. KÄNN AV DISTRO OCH UPPDATERA / INSTALLERA PROGRAM
detect_and_install() {
    echo "🔍 Identifierar operativsystem..."
    
    # Detektera via inbyggda binärer
    if command -v apt-get >/dev/null 2>&1; then
        echo "📦 Detekterade Debian/Ubuntu-baserat system (APT)."
        sudo apt-get update -y
        sudo apt-get install -y python3 curl unzip
    elif command -v dnf >/dev/null 2>&1; then
        echo "📦 Detekterade Fedora/RHEL-baserat system (DNF)."
        sudo dnf install -y python3 curl unzip
    elif command -v pacman >/dev/null 2>&1; then
        echo "📦 Detekterade Arch Linux-baserat system (Pacman)."
        sudo pacman -Syu --needed --noconfirm python curl unzip
    elif command -v zypper >/dev/null 2>&1; then
        echo "📦 Detekterade openSUSE-baserat system (Zypper)."
        sudo zypper install -y python3 curl unzip
    elif command -v apk >/dev/null 2>&1; then
        echo "📦 Detekterade Alpine Linux (APK)."
        sudo apk add python3 curl unzip
    elif command -v yum >/dev/null 2>&1; then
        echo "📦 Detekterade äldre RedHat/CentOS (YUM)."
        sudo yum install -y python3 curl unzip
    else
        echo "⚠️ Kunde inte identifiera pakethanteraren automatiskt."
        echo "Säkerställ manuellt att 'python3', 'curl' och 'unzip' är installerade."
    fi
}

# Kör installationsfunktionen
detect_and_install

echo "✅ Python och systemverktyg är verifierade!"
echo "--------------------------------------------------"

# 2. SKAPA NEDLADDNINGSMAPP
if [ ! -d "$DOWNLOAD_DIR" ]; then
    mkdir -p "$DOWNLOAD_DIR"
fi

# 3. HÄMTA SENASTE UTGÅVAN FRÅN GITHUB
echo "🔍 Söker efter senaste utgåvan av tvrdprijatelj/runcom..."

# Hämtar URL till zipball via GitHub API med robust textfiltrering (grep + sed)
ZIP_URL=$(curl -s "$API_URL" | grep '"zipball_url":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$ZIP_URL" ]; then
    echo "❌ Kunde inte hitta någon release på GitHub."
    echo "Kontrollera att du har skapat en 'Release' på: https://github.com"
    exit 1
fi

echo "📥 Laddar ner senaste källkoden..."
curl -L -o "$DOWNLOAD_DIR/runcom-latest.zip" "$ZIP_URL"

echo "📂 Extraherar källkod..."
# Skapar en ren målmapp för extraheringen
EXTRACT_TARGET="$DOWNLOAD_DIR/runcom-extracted"
mkdir -p "$EXTRACT_TARGET"

# Packar upp tyst (-q) och skriver över gamla filer om de finns (-o)
unzip -q -o "$DOWNLOAD_DIR/runcom-latest.zip" -d "$EXTRACT_TARGET"

echo "✅ Källkoden har laddats ner och extraherats!"
echo "--------------------------------------------------"

echo "=================================================="
echo "🎉 ALLT ÄR KLART!"
echo "=================================================="
echo "Mappen hittas här: $(pwd)/$EXTRACT_TARGET"
echo "Systemets Python-version: $(python3 --version)"
echo
