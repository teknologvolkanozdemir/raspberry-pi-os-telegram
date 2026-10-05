#!/usr/bin/env python3
"""Raspberry Pi OS uzaktan yönetim Telegram botu (yalnızca standart kütüphane)."""
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
CONFIRM_TTL = 60

HELP = (
    "Komutlar:\n"
    "/status - Sistem durumu\n"
    "/check - Güncellemeleri kontrol et\n"
    "/update - Güncellemeleri kur (bitince yeniden başlatır)\n"
    "/reboot - Yeniden başlat (onay gerekir)\n"
    "/shutdown - Kapat (onay gerekir)\n"
    "/confirm - Bekleyen işlemi onayla\n"
    "/cancel - Bekleyen işlemi iptal et\n"
    "/autoupdate on|off - Otomatik güncellemeyi aç/kapat\n"
    "/help - Bu mesaj"
)


def run(cmd, timeout=3600):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def parse_upgradable(output):
    """`apt list --upgradable` çıktısından paket satırlarını döndürür."""
    return [l for l in output.splitlines() if "/" in l and not l.startswith("Listing")]


class Bot:
    def __init__(self, token, admins, interval_hours=24.0, auto_update=True, runner=run):
        self.token = token
        self.admins = set(admins)
        self.interval = interval_hours * 3600
        self.auto_update = auto_update
        self.run = runner
        self.pending = {}  # chat_id -> (action, expiry)
        self.lock = threading.Lock()

    # --- Telegram ---
    def api(self, method, **params):
        url = API.format(token=self.token, method=method)
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(url, data, timeout=70) as r:
            return json.load(r)

    def send(self, chat_id, text):
        try:
            self.api("sendMessage", chat_id=chat_id, text=text[-4000:])
        except Exception as e:
            print("send hatası:", e)

    def notify(self, text):
        for a in self.admins:
            self.send(a, text)

    # --- İşlemler ---
    def status(self):
        _, up = self.run(["uptime", "-p"])
        _, load = self.run(["cat", "/proc/loadavg"])
        _, temp = self.run(["vcgencmd", "measure_temp"]) if os.path.exists("/usr/bin/vcgencmd") else (0, "n/a")
        _, disk = self.run(["df", "-h", "/"])
        return f"Çalışma süresi: {up}\nYük: {load}\nSıcaklık: {temp}\nDisk:\n{disk}\nOtomatik güncelleme: {'açık' if self.auto_update else 'kapalı'}"

    def check_updates(self):
        code, out = self.run(["sudo", "apt-get", "update"])
        if code != 0:
            return None, f"apt-get update başarısız:\n{out}"
        _, out = self.run(["apt", "list", "--upgradable"])
        return parse_upgradable(out), ""

    def do_update(self, reboot=True):
        pkgs, err = self.check_updates()
        if pkgs is None:
            self.notify(err)
            return
        if not pkgs:
            self.notify("Sistem güncel, güncelleme yok.")
            return
        self.notify(f"{len(pkgs)} güncelleme bulundu, kuruluyor...")
        code, out = self.run(["sudo", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "upgrade"])
        if code != 0:
            self.notify(f"Güncelleme başarısız:\n{out[-3000:]}")
            return
        if reboot:
            self.notify("Güncelleme tamamlandı. Sistem yeniden başlatılıyor...")
            self.run(["sudo", "systemctl", "reboot"])
        else:
            self.notify("Güncelleme tamamlandı.")

    def execute(self, action):
        if action == "reboot":
            self.notify("Sistem yeniden başlatılıyor...")
            self.run(["sudo", "systemctl", "reboot"])
        elif action == "shutdown":
            self.notify("Sistem kapatılıyor...")
            self.run(["sudo", "systemctl", "poweroff"])

    # --- Komutlar ---
    def handle(self, chat_id, text, now=None):
        now = time.time() if now is None else now
        if chat_id not in self.admins:
            return
        parts = text.strip().split()
        if not parts or not parts[0].startswith("/"):
            return
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]
        if cmd in ("/start", "/help"):
            self.send(chat_id, HELP)
        elif cmd == "/status":
            self.send(chat_id, self.status())
        elif cmd == "/check":
            pkgs, err = self.check_updates()
            if pkgs is None:
                self.send(chat_id, err)
            elif pkgs:
                self.send(chat_id, f"{len(pkgs)} güncelleme var:\n" + "\n".join(pkgs[:40]))
            else:
                self.send(chat_id, "Sistem güncel.")
        elif cmd == "/update":
            self.send(chat_id, "Güncelleme başlatıldı.")
            threading.Thread(target=self.do_update, daemon=True).start()
        elif cmd in ("/reboot", "/shutdown"):
            self.pending[chat_id] = (cmd[1:], now + CONFIRM_TTL)
            self.send(chat_id, f"{cmd[1:]} için {CONFIRM_TTL} sn içinde /confirm gönderin, iptal için /cancel.")
        elif cmd == "/confirm":
            action, exp = self.pending.pop(chat_id, (None, 0))
            if action and now <= exp:
                self.execute(action)
            else:
                self.send(chat_id, "Bekleyen işlem yok veya süresi doldu.")
        elif cmd == "/cancel":
            self.pending.pop(chat_id, None)
            self.send(chat_id, "İptal edildi.")
        elif cmd == "/autoupdate" and args and args[0].lower() in ("on", "off"):
            self.auto_update = args[0].lower() == "on"
            self.send(chat_id, f"Otomatik güncelleme {'açıldı' if self.auto_update else 'kapatıldı'}.")
        else:
            self.send(chat_id, HELP)

    def auto_loop(self):
        while True:
            time.sleep(self.interval)
            if self.auto_update:
                self.do_update()

    def poll(self):
        offset = None
        while True:
            try:
                params = {"timeout": 60}
                if offset:
                    params["offset"] = offset
                for u in self.api("getUpdates", **params).get("result", []):
                    offset = u["update_id"] + 1
                    m = u.get("message") or {}
                    if "text" in m:
                        self.handle(m["chat"]["id"], m["text"])
            except Exception as e:
                print("poll hatası:", e)
                time.sleep(5)

    def start(self):
        self.notify("Bot başlatıldı (sistem açıldı). /help ile komutları görün.")
        threading.Thread(target=self.auto_loop, daemon=True).start()
        self.poll()


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    admins = [int(x) for x in os.environ["TELEGRAM_ADMIN_IDS"].split(",") if x.strip()]
    hours = float(os.environ.get("AUTO_UPDATE_INTERVAL_HOURS", "24"))
    auto = os.environ.get("AUTO_UPDATE", "on").lower() != "off"
    Bot(token, admins, hours, auto).start()


if __name__ == "__main__":
    main()
