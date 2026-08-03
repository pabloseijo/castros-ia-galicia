#!/usr/bin/env bash
# Blindaje del disco USB externo montado en /srv/data.
#
# Sintoma observado (2026-08-03): la Raspberry responde a ping pero no a SSH,
# y Tailscale la marca offline. La causa no es la red: si el disco USB se
# desconecta o se duerme, todo proceso que toque /srv/data queda en estado D
# (uninterruptible sleep) y no se puede matar. sshd entra ahi tambien porque
# los logs y el workspace viven en ese disco, asi que la maquina parece muerta
# estando encendida.
#
# Ejecutar en la Raspberry con sudo. Idempotente: se puede repetir.
set -euo pipefail

MOUNT=/srv/data
echo "== 1. Estado actual =="
findmnt -no SOURCE,FSTYPE,OPTIONS "$MOUNT" || echo "  $MOUNT NO montado"
DEV=$(findmnt -no SOURCE "$MOUNT" 2>/dev/null || echo "")
if [ -z "$DEV" ]; then
  echo "  Buscando disco externo..."
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -E "sd[a-z]" || true
  echo "  Monta el disco antes de continuar."
  exit 1
fi
UUID=$(blkid -s UUID -o value "$DEV")
FSTYPE=$(blkid -s TYPE -o value "$DEV")
echo "  dispositivo=$DEV uuid=$UUID fs=$FSTYPE"

echo
echo "== 2. fstab por UUID, con nofail =="
# /dev/sda1 puede cambiar de letra entre arranques; UUID no.
# nofail: si el disco no esta, el arranque continua en vez de caer a emergency.
# x-systemd.device-timeout: no esperar 90s por un disco ausente.
# errors=remount-ro: ante error de E/S, remonta solo lectura en vez de colgar.
OPTS="defaults,nofail,noatime,x-systemd.device-timeout=15,x-systemd.mount-timeout=20"
case "$FSTYPE" in
  ext4|ext3|ext2) OPTS="$OPTS,errors=remount-ro" ;;
esac
LINE="UUID=$UUID $MOUNT $FSTYPE $OPTS 0 2"

cp /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d%H%M%S)"
if grep -q "UUID=$UUID" /etc/fstab; then
  sed -i "s|^UUID=$UUID.*|$LINE|" /etc/fstab
  echo "  linea actualizada"
else
  sed -i "\|[[:space:]]$MOUNT[[:space:]]|d" /etc/fstab
  echo "$LINE" >> /etc/fstab
  echo "  linea añadida"
fi
grep -E "$MOUNT|$UUID" /etc/fstab

echo
echo "== 3. Desactivar autosuspend USB =="
# La causa mas comun de que un disco USB "desaparezca" es que el kernel lo
# duerme y no despierta bien. Se desactiva para todo el bus.
cat > /etc/udev/rules.d/50-usb-storage-no-suspend.rules <<'EOF'
# Discos USB: no suspender nunca. Un disco dormido que no despierta deja
# procesos en estado D y bloquea el sistema entero.
ACTION=="add", SUBSYSTEM=="usb", ATTR{bDeviceClass}=="08", TEST=="power/control", ATTR{power/control}="on"
ACTION=="add", SUBSYSTEM=="scsi_disk", TEST=="device/power/control", ATTR{device/power/control}="on"
EOF
udevadm control --reload-rules || true
echo "  regla udev escrita"

if ! grep -q "usbcore.autosuspend=-1" /boot/firmware/cmdline.txt 2>/dev/null; then
  cp /boot/firmware/cmdline.txt "/boot/firmware/cmdline.txt.bak-$(date +%Y%m%d%H%M%S)"
  sed -i '1 s|$| usbcore.autosuspend=-1|' /boot/firmware/cmdline.txt
  echo "  usbcore.autosuspend=-1 añadido a cmdline.txt (requiere reinicio)"
else
  echo "  usbcore.autosuspend ya configurado"
fi

echo
echo "== 4. Desactivar spindown por hdparm =="
if command -v hdparm >/dev/null; then
  hdparm -S 0 "$DEV" 2>/dev/null || echo "  (el disco no admite -S, normal en SSD/USB)"
  hdparm -B 255 "$DEV" 2>/dev/null || true
else
  echo "  hdparm no instalado: apt install -y hdparm"
fi

echo
echo "== 5. Watchdog de montaje =="
# Comprueba cada minuto que el disco responde a una escritura real.
# Si no, intenta remontar y lo deja registrado. No reinicia por su cuenta:
# un reinicio automatico con el disco a medias puede corromper mas.
cat > /usr/local/bin/srv-data-watchdog.sh <<'EOF'
#!/usr/bin/env bash
MOUNT=/srv/data
STAMP="$MOUNT/.watchdog"
log() { logger -t srv-data-watchdog "$1"; }

if ! mountpoint -q "$MOUNT"; then
  log "NO montado, intentando mount"
  mount "$MOUNT" && log "remontado OK" || log "FALLO al remontar"
  exit 0
fi
# Escritura real con timeout: detecta el disco colgado, que mountpoint no ve.
if ! timeout 10 touch "$STAMP" 2>/dev/null; then
  log "ALERTA: montado pero no escribible (posible cuelgue de E/S)"
  timeout 10 mount -o remount "$MOUNT" 2>/dev/null \
    && log "remount lanzado" || log "remount fallo o colgado"
fi
EOF
chmod +x /usr/local/bin/srv-data-watchdog.sh

cat > /etc/systemd/system/srv-data-watchdog.service <<'EOF'
[Unit]
Description=Vigila que /srv/data siga montado y escribible
[Service]
Type=oneshot
ExecStart=/usr/local/bin/srv-data-watchdog.sh
EOF

cat > /etc/systemd/system/srv-data-watchdog.timer <<'EOF'
[Unit]
Description=Comprobacion de /srv/data cada minuto
[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now srv-data-watchdog.timer
echo "  watchdog activo (journalctl -t srv-data-watchdog)"

echo
echo "== 6. Sacar sshd de la dependencia del disco =="
# Si los logs y el home viven en el disco, sshd se bloquea con el.
# journald ya escribe en /var/log (SD interna), pero conviene verificarlo.
echo "  home de admin: $(getent passwd admin | cut -d: -f6)"
echo "  journald Storage: $(grep -E '^Storage' /etc/systemd/journald.conf 2>/dev/null || echo 'auto (=/var/log, SD interna) OK')"
echo
echo "  Si el home de admin estuviera en /srv/data, moverlo a la SD interna."
echo "  Un SSH que necesita leer el disco externo se cuelga con el."

echo
echo "== 7. Alimentacion =="
echo "  Comprobar under-voltage historico:"
vcgencmd get_throttled 2>/dev/null || echo "  (vcgencmd no disponible)"
echo "  0x0 = sin problemas. Cualquier otro valor: el disco USB puede estar"
echo "  quedandose sin corriente. Solucion: hub USB con alimentacion propia."

echo
echo "== HECHO =="
echo "Reinicia para aplicar usbcore.autosuspend: sudo reboot"
