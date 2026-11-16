# GAMES PLANET — ESP32 Internet Doorbell (Phase 1)

**Status: Source code prepared, not flashed, compiled, deployed or field-tested.**

This phase replaces the **Ring-side phone** with an ESP32 + a dry-contact pushbutton.
The existing **Bell-side phone** receives Internet ringing events. Video/audio are
a separate planned phase; a microcontroller button cannot emulate a PeerJS A/V call.

## Hardware

- ESP32 DevKit V1 / ESP32-WROOM-32 (30-pin), 5 V USB supply, preferably a weatherproof enclosure.
- Momentary normally-open doorbell button: **GPIO27 → button → GND**.
- Optional setup/reset button: **GPIO26 → button → GND**, hold for more than six seconds.
- No resistor is required for a short, clean indoor switch: `INPUT_PULLUP` is enabled.
  For long outdoor wires, use protection, filtering, and ideally optoisolation.
- **Do not feed 5 V, 12 V or mains voltage into GPIO.** The switch is a dry contact.

## Cloud relay (required)

1. Create a Cloudflare account and install Node.js 20+.
2. From this folder run `npx wrangler login`.
3. Run `npx wrangler kv namespace create RING_EVENTS`.
4. Copy the returned namespace ID into `wrangler.toml`; uncomment the `[[kv_namespaces]]` block.
5. Generate a random **at least 32-character** secret using a cryptographically secure password generator. **Never commit the secret.**
6. Run `npx wrangler secret put DEVICE_TOKEN` and enter that secret.
7. Deploy using `npx wrangler deploy`. Record your `https://...workers.dev` URL.
8. Verify that `https://...workers.dev/health` returns `{"status":"online"}`.

Worker API: authenticated `POST /ring` and `GET /events`.
The Worker uses Cloudflare Workers KV, which is eventually consistent and does not
guarantee instant cross-region delivery. The Bell receiver polls about every 2.5 s
while the Bell page is running in the foreground.

## Flash firmware

1. Install Arduino IDE 2.x and **Espressif esp32 board package 3.x**.
2. Open `GamesPlanetDoorbell.ino`; choose `ESP32 Dev Module` / your actual board.
3. Build and upload through the board's programming USB port.
4. This firmware uses ESP-IDF's certificate bundle via `esp_crt_bundle_attach`.
   A compatible Arduino-ESP32 build with the certificate bundle enabled is necessary.
   **Do not turn off TLS certificate checking.**
5. At first boot, join Wi-Fi hotspot `GP-BELL-XXXX` with password `GPBellSetup`.
6. Open `http://192.168.4.1` in Chrome. Select a nearby 2.4 GHz Wi-Fi SSID,
   enter its password, Worker URL and the same `DEVICE_TOKEN`; press Save.
7. ESP32 restarts and joins your Wi-Fi. If a reset is necessary, hold the GPIO26
   setup switch for 6+ seconds. This deletes stored credentials and secret.

## Bell app/page setup

Open `https://gamesplanet13.github.io/PAYMENT/ring-bell/bell.html`
and expand **ESP32 Doorbell · Internet Setup**.
Enter the exact Worker URL and the same token, press **Save IoT Connection**.
When the page is active, a fresh ESP32 button press starts the Bell tone.

**Existing APK v7 is bundled/offline** and does NOT receive these HTML/JS changes
without a new signed APK build. A new APK is not included here.

## What remains for production

- Real ESP32 hardware compile and field test.
- Cloudflare Worker deployment and credential provisioning.
- New **signed** Bell APK and foreground service integration.
- A reliable system push notification (FCM) for ringing when the app is
  suspended or killed. Browser polling is not equivalent to a background push.
- Battery/power-loss resilience, enclosure, weather and ESD protection.

## Phase 2 & 3 options

- ESP32-S3 **with external PSRAM and native USB Host**: USB UVC MJPEG cameras
  (only compatible cameras, often limited resolution/frame rate); USB Host power
  and optional separate audio design are necessary. Real-time A/V with existing
  Bell PeerJS is a substantial new protocol/bridge.
- Raspberry Pi Zero 2 W or other Linux SBC with USB OTG host, Wi-Fi and
  UVC/UAC device support: easier USB Webcam and USB microphone/speaker handling,
  and can run native WebRTC gateway software.
- For lowest camera cost with **non-USB** camera, ESP32-CAM with OV2640.
  Suitable for video prototypes, not as a drop-in USB Webcam controller.
