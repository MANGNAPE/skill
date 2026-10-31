#!/usr/bin/env sh
# Sauvegarde cohérente de la base SQLite (sans arrêter le serveur).
# Usage : SKILLUP_DB=/data/skillup.db ./backup.sh /chemin/vers/dossier_backup
set -eu
DB="${SKILLUP_DB:-skillup.db}"
DEST="${1:-backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
python3 - "$DB" "$DEST/skillup-$STAMP.db" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
EOF
# Ne garde que les 14 dernières sauvegardes
ls -1t "$DEST"/skillup-*.db 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Sauvegarde créée : $DEST/skillup-$STAMP.db"
