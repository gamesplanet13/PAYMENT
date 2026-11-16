# GAMES PLANET — TWO ESP32 RING/BELL: LAN + INTERNET
Status: combined firmware committed, **not compiled/flashed/tested**. Cloud relay is **not deployed**.

## Purchase
- ESP32 DevKit V1 (30-pin) **2 pieces**, preferably matching micro-USB/type-C variants for each power lead
- Momentary normally-open pushbutton **1**, waterproof/IP-rated if mounted outdoors
- **3.3V-compatible active-HIGH trigger** buzzer module **1** (VCC/GND/IN). Many cheap active buzzer boards are **LOW-LEVEL-triggered**; do not substitute without modifying output logic
- Momentary normally-open Silence pushbutton **1** for BELL
- Optional reset switches **2**, enclosures **2**, USB leads **2**, regulated 5V USB wall adaptors **2**, wires and terminal blocks, suitable switch protection on long/exposed outdoor wires
- Wi-Fi router(s) with **2.4GHz** and Internet access for remote mode

## Firmware
[ESP32RingBellDualWiFiInternet.ino](ESP32RingBellDualWiFiInternet.ino)
Use Arduino IDE 2 + Espressif Arduino-ESP32 board package 3.x.
Open the sketch. Set `#define ROLE_RING 1` and upload to the door ESP32.
Set `#define ROLE_RING 0` and upload to the buzzer ESP32.
Choose correct board/USB port; connect each board via programming USB.

## Wiring
| RING ESP32 | Wiring |
| --- | --- |
| GPIO27 | Momentary normally-open button to GND |
| GPIO26 | Optional reset/setup button to GND; hold >6 s |
| USB | regulated 5 V power |

| BELL ESP32 | Wiring |
| --- | --- |
| GPIO25 | IN pin of **3.3 V-compatible active-HIGH** buzzer module |
| 3V3 | buzzer module 3.3V VCC |
| GND | buzzer GND, silence button return |
| GPIO33 | momentary normally-open Silence pushbutton to GND |
| GPIO26 | optional reset/setup pushbutton to GND |
| USB | regulated 5 V power |

**Check buzzer trigger polarity**. A low-level-trigger module sounds with LOW
and will require firmware polarity inversion; an active bare buzzer / high-power
sounder needs an external transistor/MOSFET driver and flyback protection if inductive.
GPIO is **3.3 V logic**, NOT mains/12 V/5 V tolerant.

## Initial setup
Each board creates a temporary configuration hotspot:
RING: `GP-RING-XXXX`; BELL: `GP-BELL-XXXX`.
Both use setup password `GPBellSetup`.
Connect phone/laptop to each setup Wi-Fi in turn, visit
`http://192.168.4.1`, choose nearby 2.4 GHz Wi-Fi, enter credentials.
Enter the SAME random 32+ character **local pairing secret** on both boards.
To use **remote Internet** too, enter identical Cloudflare Worker URL
and its separate DEVICE_TOKEN on both boards.
Once saved, both boards reboot into normal Wi-Fi mode.

**Same LAN:** ESP32 RING sends signed UDP broadcast directly to BELL; no
Internet required; both boards on same broadcast domain and client isolation OFF.
**Different Internet networks:** RING sends HTTPS POST /ring to Worker and
BELL fetches GET /events (poll interval around 2.2 sec); router/NAT port
forwarding not needed. Internet latency, outage or Workers KV consistency may
delay or miss alerts; use a proper push/queue backend for production-grade alarm use.

## Internet relay setup
1. Configure Cloudflare Worker from `cloudflare-worker.js`, KV namespace
`RING_EVENTS`, and `DEVICE_TOKEN` secret (see README.md in folder).
2. Deploy it. Its HTTPS endpoint will be supplied by Cloudflare.
3. Enter this URL and the matching token on BOTH ESP32 devices.
4. Keep the local pairing secret the SAME on both devices (not used by cloud).
5. Test the LAN path, then test different Wi-Fi/hotspots with the Worker.

The current relay stores one latest event, not a durable message queue.
Not guaranteed delivery. No phone app, camera or two-way talk is needed for
this hardware-only bell setup. Existing phone Bell App remains a separate
optional receiver, not a prerequisite.

## Important
Source is a development prototype. The combined sketch has **not been built
against an Arduino toolchain or verified on real boards**. Do not claim
ready-to-flash verified binaries or successful over-Internet tests.
