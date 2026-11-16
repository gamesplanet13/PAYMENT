/*
 Games Planet ESP32 Wi-Fi Doorbell, phase 1: BUTTON -> INTERNET -> BELL APP
 Board: ESP32 DevKit V1 / ESP32-WROOM-32 (Arduino-ESP32 3.x).
 Doorbell NO (normally-open) momentary dry switch: GPIO27 <-> GND.
 Setup/reset switch: GPIO26 <-> GND (hold >6s while powered).
 USB 5V power. NEVER connect mains/12V/5V directly to GPIO.
 Requires a Cloudflare Worker, DEVICE_TOKEN and RING_EVENTS KV deployment.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <esp_http_client.h>
#include <esp_crt_bundle.h>
#include <time.h>

#define DOOR_PIN 27
#define CONFIG_PIN 26
static const uint16_t DNS_PORT = 53;
Preferences prefs;
WebServer web(80);
DNSServer dns;
String wifiSSID,wifiPassword,relayUrl,deviceToken;
bool portal=false,buttonWasDown=false;
unsigned long edgeAt=0,configStart=0,lastPost=0,lastWifiAttempt=0;
bool configWasDown=false;
String uniqueAP(){
 uint64_t id=ESP.getEfuseMac();
 char buf[24];snprintf(buf,sizeof(buf),"GP-BELL-%04X",(unsigned int)(id&0xFFFF));
 return String(buf);
}
String esc(String v){
 v.replace("&","&amp;");v.replace("<","&lt;");v.replace(">","&gt;");
 v.replace("\"","&quot;");v.replace("'","&#39;");return v;
}
String setupHTML(){
 String html=R"HTML(<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Games Planet Doorbell Setup</title><style>
 body{background:#101820;color:#fff;font:16px system-ui;max-width:540px;margin:auto;padding:22px}
 label{display:block;margin:14px 0}input,select,button{display:block;width:100%;padding:12px;border-radius:8px;font:inherit;box-sizing:border-box}
 button{background:#e7be63;color:#000;border:0;font-weight:700}small{color:#c4ccd4}
 </style></head><body><h2>GAMES PLANET · Doorbell Setup</h2><p>Select nearby Wi-Fi and save the Internet relay details.</p><form method="post" action="/save"><label>Nearby Wi-Fi<select name="ssid">)HTML";
 int found=WiFi.scanNetworks(false,true);
 for(int i=0;i<found && i<35;i++){
   String n=WiFi.SSID(i);
   html+="<option value=\""+esc(n)+"\""+(n==wifiSSID?" selected":"")+">"+esc(n)+" ("+String(WiFi.RSSI(i))+" dBm)</option>";
 }
 html+="</select></label>";
 html+="<label>Wi-Fi password<input name=\"password\" type=\"password\" maxlength=\"63\" placeholder=\"Enter Wi-Fi password\" value=\""+esc(wifiPassword)+"\"></label>";
 html+="<label>Worker HTTPS URL<input name=\"relay\" type=\"url\" required placeholder=\"https://your-worker.workers.dev\" value=\""+esc(relayUrl)+"\"></label>";
 html+="<label>Device secret / same token configured on Worker<input name=\"token\" type=\"password\" minlength=\"32\" maxlength=\"128\" required value=\""+esc(deviceToken)+"\"></label>";
 html+="<button type=\"submit\">Save and Connect</button></form><p><small>Connect your Bell App to the same Worker URL + token. Only use a trusted Wi-Fi network. Setup hotspot turns off after connection.</small></p></body></html>";
 return html;
}
void startPortal(){
 portal=true;WiFi.mode(WIFI_AP_STA);
 WiFi.softAP(uniqueAP().c_str(),"GPBellSetup");
 dns.start(DNS_PORT,"*",WiFi.softAPIP());
 web.on("/",HTTP_GET,[]{web.send(200,"text/html; charset=utf-8",setupHTML());});
 web.on("/generate_204",HTTP_GET,[]{web.sendHeader("Location","/",true);web.send(302,"text/plain","");});
 web.on("/hotspot-detect.html",HTTP_GET,[]{web.sendHeader("Location","/",true);web.send(302,"text/plain","");});
 web.on("/save",HTTP_POST,[]{
   String ssid=web.arg("ssid"),password=web.arg("password"),url=web.arg("relay"),token=web.arg("token");
   url.trim();url.replace(" ","");
   if(!ssid.length()||ssid.length()>32||!url.startsWith("https://")||url.length()>180||
      token.length()<32||token.length()>128){
    web.send(400,"text/plain","Invalid configuration; use an HTTPS Worker URL and 32+ character token.");return;
   }
   while(url.endsWith("/"))url.remove(url.length()-1);
   prefs.begin("gp-doorbell",false);
   prefs.putString("ssid",ssid);prefs.putString("pwd",password);
   prefs.putString("relay",url);prefs.putString("token",token);
   prefs.end();
   web.send(200,"text/html","<h2>Saved. ESP32 will connect to Wi-Fi. You may close this page.</h2>");
   delay(900);ESP.restart();
 });
 web.onNotFound([]{web.sendHeader("Location","/",true);web.send(302,"text/plain","");});
 web.begin();Serial.println("SETUP AP: "+uniqueAP()+" / GPBellSetup / http://192.168.4.1");
}
bool connected(){
 return WiFi.status()==WL_CONNECTED;
}
void load(){
 prefs.begin("gp-doorbell",true);
 wifiSSID=prefs.getString("ssid","");
 wifiPassword=prefs.getString("pwd","");
 relayUrl=prefs.getString("relay","");
 deviceToken=prefs.getString("token","");
 prefs.end();
}
void sendBell(){
 if(!connected()||!relayUrl.startsWith("https://")||deviceToken.length()<32)return;
 // ESP-IDF certificate bundle validates the public HTTPS server's certificate.
 esp_http_client_config_t cfg={};
 String endpoint=relayUrl+"/ring";
 cfg.url=endpoint.c_str();
 cfg.method=HTTP_METHOD_POST;
 cfg.timeout_ms=8000;
 cfg.crt_bundle_attach=esp_crt_bundle_attach;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);
 if(!client)return;
 String auth="Bearer "+deviceToken;
 esp_http_client_set_header(client,"Authorization",auth.c_str());
 esp_http_client_set_header(client,"Content-Type","application/json");
 esp_http_client_set_post_field(client,"{}",2);
 esp_err_t result=esp_http_client_perform(client);
 int status=esp_http_client_get_status_code(client);
 Serial.printf("Bell trigger: esp=%d HTTP=%d\n",(int)result,status);
 esp_http_client_cleanup(client);
}
void setup(){
 Serial.begin(115200);
 pinMode(DOOR_PIN,INPUT_PULLUP);pinMode(CONFIG_PIN,INPUT_PULLUP);
 load();
 if(!wifiSSID.length()||!relayUrl.length()||deviceToken.length()<32){startPortal();return;}
 WiFi.mode(WIFI_STA);WiFi.begin(wifiSSID.c_str(),wifiPassword.c_str());
 unsigned long start=millis();
 while(!connected()&&millis()-start<14000)delay(250);
 if(!connected())startPortal();
 else Serial.println("Wi-Fi connected: "+WiFi.localIP().toString());
}
void loop(){
 unsigned long now=millis();
 if(portal){dns.processNextRequest();web.handleClient();}
 if(!connected()&&!portal&&now-lastWifiAttempt>10000){
   lastWifiAttempt=now;WiFi.reconnect();
 }
 // Keep portal available on connectivity loss, but avoid unsecured public access.
 if(!connected()&&!portal&&now>90000){startPortal();}
 bool cfg= digitalRead(CONFIG_PIN)==LOW;
 if(cfg&&!configWasDown)configStart=now;
 if(cfg&&configWasDown&&now-configStart>6000){
   prefs.begin("gp-doorbell",false);prefs.clear();prefs.end();delay(100);ESP.restart();
 }
 configWasDown=cfg;
 bool down=digitalRead(DOOR_PIN)==LOW;
 if(down&&!buttonWasDown){edgeAt=now;}
 if(down&&buttonWasDown&&edgeAt&&now-edgeAt>65&&now-lastPost>4000){
   lastPost=now;edgeAt=0;sendBell();
 }
 if(!down)edgeAt=0;
 buttonWasDown=down;
 delay(5);
}
