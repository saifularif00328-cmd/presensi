#!/usr/bin/env bash
# ============================================================================
#  Cloudflare Tunnel untuk VPS tanpa dashboard Zero Trust (tanpa kartu/PayPal).
#  Langkah:
#    1. cloudflared tunnel login      (buka tautan yang muncul, pilih domain, Authorize)
#    2. bash tunnel_vps.sh            (atau: curl -fsSL <url>/deploy/tunnel_vps.sh | bash)
#  Hasil: https://presensiku.biz.id -> Nginx 127.0.0.1:8080. Aman diulang.
# ============================================================================
set -euo pipefail
DOMAIN="${DOMAIN:-presensiku.biz.id}"
NAMA="${NAMA_TUNNEL:-vps}"

[ "$(id -u)" = 0 ] || { echo "Jalankan sebagai root"; exit 1; }
[ -f /root/.cloudflared/cert.pem ] || {
  echo "Belum login ke Cloudflare. Jalankan dulu:  cloudflared tunnel login"; exit 1; }

id_tunnel() {
  { cloudflared tunnel list --output json 2>/dev/null || echo '[]'; } | python3 -c "
import sys, json
try:
    daftar = json.load(sys.stdin) or []
except ValueError:
    daftar = []
print(next((t['id'] for t in daftar if t.get('name') == '$NAMA'), ''))"
}

echo "==> Tunnel '$NAMA'"
ID=$(id_tunnel)
if [ -z "$ID" ]; then
  cloudflared tunnel create "$NAMA"
  ID=$(id_tunnel)
fi
[ -n "$ID" ] || { echo "Gagal membuat tunnel"; exit 1; }
echo "    id: $ID"

[ -f "/root/.cloudflared/$ID.json" ] || {
  echo "File kunci tunnel /root/.cloudflared/$ID.json tidak ada."
  echo "Hapus tunnel lama:  cloudflared tunnel delete $NAMA   lalu jalankan skrip ini lagi."; exit 1; }

echo "==> DNS $DOMAIN -> tunnel"
cloudflared tunnel route dns --overwrite-dns "$NAMA" "$DOMAIN"

echo "==> Konfigurasi /etc/cloudflared/config.yml"
mkdir -p /etc/cloudflared
cp "/root/.cloudflared/$ID.json" "/etc/cloudflared/$ID.json"
chmod 600 "/etc/cloudflared/$ID.json"
cat > /etc/cloudflared/config.yml <<EOF
tunnel: $ID
credentials-file: /etc/cloudflared/$ID.json
ingress:
  - hostname: $DOMAIN
    service: http://localhost:8080
  - service: http_status:404
EOF

echo "==> Layanan cloudflared"
if [ -f /etc/systemd/system/cloudflared.service ]; then
  systemctl restart cloudflared
else
  cloudflared --config /etc/cloudflared/config.yml service install
fi
sleep 5
systemctl is-active --quiet cloudflared && echo "    cloudflared: aktif" || {
  echo "cloudflared belum aktif — lihat: journalctl -u cloudflared -n 30"; exit 1; }

cat <<EOF

============================================================
 SELESAI. Buka https://$DOMAIN  (tunggu 1-2 menit bila belum tampil)
============================================================
EOF
