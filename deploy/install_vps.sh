#!/usr/bin/env bash
# ============================================================================
#  Pemasangan server VPS Presensi (Ubuntu 22.04 / 24.04) — jalankan sebagai root:
#     curl -fsSL <url-repo>/deploy/install_vps.sh | bash      (atau)
#     bash deploy/install_vps.sh
#  Aman diulang (untuk memperbarui aplikasi juga).
#
#  Hasil:
#   - MariaDB (hanya localhost), Nginx di 127.0.0.1:8080, Python venv di /opt/presensi
#   - user sistem "presensi", data sekolah di /srv/presensi/<kode>/
#   - firewall: hanya SSH yang terbuka; web masuk lewat Cloudflare Tunnel
#   - backup harian semua sekolah (03.00) ke /srv/presensi/_backup
#  Setelah itu: tambahkan sekolah dengan  presensi-sekolah tambah <kode> --nama "..."
# ============================================================================
set -euo pipefail
REPO_URL="${REPO_URL:-https://github.com/saifularif00328-cmd/presensi.git}"
BRANCH="${BRANCH:-claude/aplikasi-sesuai-prd-bppvd6}"
APP=/opt/presensi

[ "$(id -u)" = 0 ] || { echo "Jalankan sebagai root (sudo -i)"; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "==> Paket sistem"
apt-get update -q
apt-get install -y -q mariadb-server nginx python3-venv python3-pip git ufw curl

echo "==> User & folder"
id presensi >/dev/null 2>&1 || useradd --system --home /srv/presensi --shell /usr/sbin/nologin presensi
mkdir -p /srv/presensi/_backup
chown presensi:presensi /srv/presensi /srv/presensi/_backup

echo "==> Kode aplikasi ($BRANCH)"
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch -q origin "$BRANCH" && git -C "$APP" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q -b "$BRANCH" "$REPO_URL" "$APP"
fi
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt" waitress
ln -sf "$APP/tools/sekolah.py" /usr/local/bin/presensi-sekolah
chmod +x "$APP/tools/sekolah.py"

echo "==> MariaDB hanya untuk localhost"
cat > /etc/mysql/mariadb.conf.d/60-presensi.cnf <<'EOF'
[mysqld]
bind-address = 127.0.0.1
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
innodb_buffer_pool_size = 256M
max_connections = 200
EOF
systemctl enable --now mariadb
systemctl restart mariadb

echo "==> systemd & Nginx"
cp "$APP/deploy/presensi@.service" /etc/systemd/system/
systemctl daemon-reload
cp "$APP/deploy/nginx-presensi.conf" /etc/nginx/conf.d/presensi.conf
touch /etc/nginx/presensi-sekolah.map
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> Firewall (hanya SSH)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null

echo "==> Cloudflare Tunnel (cloudflared)"
if ! command -v cloudflared >/dev/null; then
  curl -fsSL -o /tmp/cloudflared.deb \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  dpkg -i /tmp/cloudflared.deb
fi

echo "==> Backup harian 03.00"
cat > /etc/cron.d/presensi-backup <<'EOF'
0 3 * * * root /usr/local/bin/presensi-sekolah backup --semua >> /var/log/presensi-backup.log 2>&1
EOF

cat <<'EOF'

============================================================
 SELESAI. Langkah berikutnya:
 1. Hubungkan VPS ke Cloudflare (sekali):
      cloudflared service install <TOKEN-TUNNEL-VPS>
    Di dashboard Cloudflare, tunnel VPS: Public hostname
      *.presensiku.biz.id  ->  http://localhost:8080
 2. Tambah sekolah:
      presensi-sekolah tambah smpn1 --nama "SMP Negeri 1" --hari 365
 3. Pindah sekolah dari server sekolah (file backup ZIP dari menu Backup):
      presensi-sekolah pindah smpn1 /root/presensi-backup-smpn1.zip
============================================================
EOF
