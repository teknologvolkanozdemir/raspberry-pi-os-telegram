# raspberry-pi-os-telegram
bilgisayarı uzaktan kapatır, yeniden başlatır, güncellemeleri kontrol eder, günceller.

## Kurulum
Yalnızca Python 3 standart kütüphanesini kullanır.

```
export TELEGRAM_BOT_TOKEN=<BotFather token>
export TELEGRAM_ADMIN_IDS=<yönetici chat id, virgülle ayrılmış>
export AUTO_UPDATE_INTERVAL_HOURS=24   # isteğe bağlı
export AUTO_UPDATE=on                  # on|off
python3 bot.py
```
Bot kullanıcısı parolasız `sudo` ile `apt-get` ve `systemctl` çalıştırabilmelidir (systemd servisi olarak root çalıştırılması da uygundur).

Komutlar: `/status /check /update /reboot /shutdown /confirm /cancel /autoupdate on|off /help`.
Otomatik güncelleme: periyodik kontrol, güncelleme varsa kurar ve yeniden başlatır; tüm adımlar yöneticiye bildirilir.

Test: `python3 -m unittest discover tests`
