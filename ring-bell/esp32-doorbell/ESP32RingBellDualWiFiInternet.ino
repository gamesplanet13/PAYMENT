/* For dual LAN + Internet operation, configure both boards with
 * the SAME Wi-Fi? They may also use DIFFERENT networks; cloud relay
 * provides remote delivery. LAN broadcast is used only when reachable.
 * No phone is required.
 */
/*
 GAMES PLANET - standalone RING <-> BELL on the SAME Wi-Fi LAN.
 Flash two ESP32 DevKit V1 boards with this sketch:
 set ROLE_RING=1 on door unit, ROLE_RING=0 on buzzer unit.
 Needs no phone, cloud, MQTT or Internet once configured.
 Arduino ESP32 board package 3.x.
 Ring: GPIO27 -> normally-open button -> GND.
 Bell: active-high *input-trigger* 3.3V buzzer module IN->GPIO25,
       module VCC->3V3, GND->GND.
 Bell silence: GPIO33 -> normally-open button -> GND.
 Both: CONFIG RESET GPIO26 -> button -> GND (>6 seconds).
 GPIO outputs are 3.3V ONLY, never attach a raw high-current bell to GPIO.
 Wi-Fi AP provisioning: GP-RING-XXXX / GP-BELL-XXXX; password GPBellSetup.
 Shared secret should be >=32 random chars, same in both devices.
*/
#define ROLE_RING 1 // Flash second board with 0 for BELL
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <esp_http_client.h>
#include <esp_crt_bundle.h>
#include <mbedtls/md.h>
#define RING_PIN 27
#define BUZZER_PIN 25
#define SILENCE_PIN 33
#define RESET_PIN 26
#define PORT 42123

WiFiUDP udp;
WebServer portalServer(80);
DNSServer dns;
Preferences settings;
String ssid,password,pairSecret,cloudURL,cloudToken,cloudSeen;
bool cloudFirst=true;
unsigned long cloudPollAt=0, lastCloudRingAt=0;
bool portal=false;
bool wasDown=false,ringing=false;
unsigned long buttonAt=0,resetAt=0,lastPress=0,lastWiFi=0,ringAt=0,lastSent=0;
uint32_t lastNonce=0;
String apSSID(){
 char name[24];
 snprintf(name,sizeof(name),ROLE_RING?"GP-RING-%04X":"GP-BELL-%04X",(unsigned int)(ESP.getEfuseMac()&0xFFFF));
 return String(name);
}
String escapeHTML(String x){
 x.replace("&","&amp;");x.replace("<","&lt;");x.replace(">","&gt;");x.replace("\"","&quot;");x.replace("'","&#39;");
 return x;
}
String digest(String data){
 byte h[32];
 mbedtls_md_context_t ctx;mbedtls_md_init(&ctx);
 const mbedtls_md_info_t* info=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
 if(!info){mbedtls_md_free(&ctx);return "";}
 if(mbedtls_md_setup(&ctx,info,1)!=0){mbedtls_md_free(&ctx);return "";}
 mbedtls_md_hmac_starts(&ctx,(const byte*)pairSecret.c_str(),pairSecret.length());
 mbedtls_md_hmac_update(&ctx,(const byte*)data.c_str(),data.length());
 mbedtls_md_hmac_finish(&ctx,h);
 mbedtls_md_free(&ctx);
 char hex[65];for(int i=0;i<32;i++)sprintf(hex+i*2,"%02x",h[i]);hex[64]=0;
 return String(hex);
}
void load(){
 settings.begin("gp-rb-lan",true);
 ssid=settings.getString("ssid","");
 password=settings.getString("pwd","");
 pairSecret=settings.getString("key","");
 cloudURL=settings.getString("relay","");cloudToken=settings.getString("token","");cloudSeen=settings.getString("seen","");
 settings.end();
}
void beginPortal(){
 portal=true;
 WiFi.mode(WIFI_AP_STA);
 WiFi.softAP(apSSID().c_str(),"GPBellSetup");
 dns.start(53,"*",WiFi.softAPIP());
 portalServer.on("/",HTTP_GET,[](){
  String html=R"html(<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Games Planet Ring Bell WiFi</title><style>body{background:#101825;color:white;font:16px system-ui;padding:22px;max-width:560px;margin:auto}
  label{display:block;margin:14px 0}input,select,button{width:100%;box-sizing:border-box;padding:12px;font:inherit}
  button{background:#ecca6a;border:0;border-radius:8px}</style></head><body>
  <h2>GAMES PLANET - )html";
  html+=(ROLE_RING?"RING (Button)":"BELL (Buzzer)");
  html+=R"html(</h2><p>Both devices must join the same 2.4 GHz Wi-Fi router. Both must use the exact same shared secret.</p>
  <form action="/save" method="post"><label>Nearby Wi-Fi<select name="ssid">)html";
  int n=WiFi.scanNetworks(false,true);
  for(int i=0;i<n&&i<35;i++){
   String a=WiFi.SSID(i);
   html+="<option value=\""+escapeHTML(a)+"\">"+escapeHTML(a)+" ("+String(WiFi.RSSI(i))+" dBm)</option>";
  }
  html+="</select></label><label>Wi-Fi password<input type=\"password\" name=\"password\" maxlength=\"63\"></label>";
  html+="<label>Shared pairing secret (32-128 characters, SAME on both)<input name=\"secret\" type=\"password\" minlength=\"32\" maxlength=\"128\" required></label>";
  html+="<label>Internet Worker HTTPS URL (optional for local-only)<input name=\"relay\" type=\"url\" placeholder=\"https://your-worker.workers.dev\" value=\""+escapeHTML(cloudURL)+"\"></label>";
  html+="<label>Internet Device Secret (same on both boards)<input name=\"token\" type=\"password\" minlength=\"32\" maxlength=\"128\" value=\""+escapeHTML(cloudToken)+"\"></label>";
  html+="<button>Save & Connect</button></form></body></html>";
  portalServer.send(200,"text/html; charset=utf-8",html);
 });
 portalServer.on("/save",HTTP_POST,[](){
  String s=portalServer.arg("ssid"),p=portalServer.arg("password"),k=portalServer.arg("secret");
  String relay=portalServer.arg("relay"),token=portalServer.arg("token");relay.trim();while(relay.endsWith("/"))relay.remove(relay.length()-1);
  if(s.isEmpty()||s.length()>32||k.length()<32||k.length()>128||(!relay.isEmpty()&&(!relay.startsWith("https://")||token.length()<32||token.length()>128))){
   portalServer.send(400,"text/plain","WiFi SSID and long pairing secret required");return;
  }
  settings.begin("gp-rb-lan",false);
  settings.putString("ssid",s);settings.putString("pwd",p);settings.putString("key",k);
  settings.putString("relay",relay);settings.putString("token",token);
  settings.end();
  portalServer.send(200,"text/html","Saved. Device will connect now.");
  delay(700);ESP.restart();
 });
 portalServer.onNotFound([](){portalServer.sendHeader("Location","/",true);portalServer.send(302,"text/plain","");});
 portalServer.begin();
 Serial.println("SETUP HOTSPOT "+apSSID()+" / GPBellSetup / http://192.168.4.1");
}
IPAddress broadcastAddress(){
 IPAddress ip=WiFi.localIP(),mask=WiFi.subnetMask(),b;
 for(int i=0;i<4;i++)b[i]=(uint8_t)(ip[i]|(uint8_t)~mask[i]);
 return b;
}
static esp_err_t onCloudData(esp_http_client_event_t *e){
 if(e->event_id==HTTP_EVENT_ON_DATA&&e->user_data&&e->data&&e->data_len>0){
  String* out=static_cast<String*>(e->user_data);if(out->length()<4096)out->concat((const char*)e->data,e->data_len);
 }
 return ESP_OK;
}
bool cloudRequest(const char* endpoint,bool post,String &response){
 if(cloudURL.isEmpty()||cloudToken.length()<32||WiFi.status()!=WL_CONNECTED)return false;
 String url=cloudURL+endpoint;
 esp_http_client_config_t cfg={};
 cfg.url=url.c_str();cfg.crt_bundle_attach=esp_crt_bundle_attach;
 cfg.timeout_ms=5000;cfg.event_handler=onCloudData;cfg.user_data=&response;
 cfg.method=post?HTTP_METHOD_POST:HTTP_METHOD_GET;
 esp_http_client_handle_t c=esp_http_client_init(&cfg);if(!c)return false;
 String auth="Bearer "+cloudToken;
 esp_http_client_set_header(c,"Authorization",auth.c_str());
 if(post){esp_http_client_set_header(c,"Content-Type","application/json");esp_http_client_set_post_field(c,"{}",2);}
 esp_err_t err=esp_http_client_perform(c);int status=esp_http_client_get_status_code(c);
 esp_http_client_cleanup(c);
 return err==ESP_OK&&status==200;
}
String latestEventId(const String& response){
 int ev=response.indexOf("\"event\"");if(ev<0)return "";
 int id=response.indexOf("\"id\"",ev);if(id<0)return "";
 int colon=response.indexOf(':',id);if(colon<0)return "";
 int start=response.indexOf('"',colon+1);if(start<0)return "";
 int stop=response.indexOf('"',start+1);if(stop<0||stop-start>90)return "";
 return response.substring(start+1,stop);
}
void pollCloud(){
 String response;if(!cloudRequest("/events",false,response))return;
 String id=latestEventId(response);if(id.isEmpty())return;
 if(cloudFirst){
  cloudFirst=false;
  if(cloudSeen.isEmpty()){cloudSeen=id;settings.begin("gp-rb-lan",false);settings.putString("seen",id);settings.end();return;}
 }
 if(id==cloudSeen)return;
 cloudSeen=id;settings.begin("gp-rb-lan",false);settings.putString("seen",id);settings.end();
 // Local UDP may have already rung this doorbell.
 if(millis()-ringAt>3200||!ringing){ringing=true;ringAt=millis();}
}
void sendRing(){
 if(WiFi.status()!=WL_CONNECTED)return;
 uint32_t nonce=esp_random();
 if(nonce==lastNonce)nonce++;
 lastNonce=nonce;
 String data="GPB1|"+String(nonce,HEX);
 String payload=data+"|"+digest(data);
 // Redundant UDP frames; duplicate nonces are ignored by Bell.
 for(int i=0;i<3;i++){
  udp.beginPacket(broadcastAddress(),PORT);
  udp.print(payload);udp.endPacket();delay(35);
 }
 Serial.println("Ring sent over local Wi-Fi");
 // Also publish via Internet. LAN acts instantly; Internet covers remote Wi-Fi.
 if(!cloudURL.isEmpty()){String response;bool ok=cloudRequest("/ring",true,response);Serial.println(ok?"Internet ring posted":"Internet ring retry needed");}
}
void silence(){ringing=false;digitalWrite(BUZZER_PIN,LOW);}
void receiveRing(){
 int bytes=udp.parsePacket();
 if(bytes<=0)return;
 if(bytes>160){while(udp.available())udp.read();return;}
 char buf[161];int n=udp.read(buf,sizeof(buf)-1);if(n<=0)return;buf[n]=0;
 String packet(buf);
 int first=packet.indexOf('|'),second=packet.indexOf('|',first+1);
 if(first<0||second<0||packet.substring(0,first)!="GPB1")return;
 String noncePart=packet.substring(first+1,second),mac=packet.substring(second+1);
 if(noncePart.isEmpty()||noncePart.length()>8||mac.length()!=64)return;
 String check=digest(packet.substring(0,second));
 unsigned diff=0;for(int i=0;i<64;i++)diff|=(uint8_t)check[i]^(uint8_t)mac[i];
 if(diff)return;
 uint32_t nonce=(uint32_t)strtoul(noncePart.c_str(),nullptr,16);
 if(nonce==lastNonce)return;
 lastNonce=nonce;
 ringing=true;ringAt=millis();
 Serial.println("RING RECEIVED -> bell sounding");
}
void setup(){
 Serial.begin(115200);
 pinMode(RESET_PIN,INPUT_PULLUP);
 pinMode(RING_PIN,INPUT_PULLUP);
 pinMode(SILENCE_PIN,INPUT_PULLUP);
 pinMode(BUZZER_PIN,OUTPUT);digitalWrite(BUZZER_PIN,LOW);
 load();
 if(ssid.isEmpty()||pairSecret.length()<32){beginPortal();return;}
 WiFi.mode(WIFI_STA);WiFi.begin(ssid.c_str(),password.c_str());
 unsigned long started=millis();
 while(WiFi.status()!=WL_CONNECTED&&millis()-started<12000)delay(200);
 if(WiFi.status()!=WL_CONNECTED)beginPortal();
 else {udp.begin(PORT);Serial.println(WiFi.localIP());}
}
void loop(){
 unsigned long now=millis();
 if(portal){dns.processNextRequest();portalServer.handleClient();}
 if(digitalRead(RESET_PIN)==LOW){
  if(!resetAt)resetAt=now;
  if(now-resetAt>6000){settings.begin("gp-rb-lan",false);settings.clear();settings.end();ESP.restart();}
 }else resetAt=0;
 if(!portal&&WiFi.status()!=WL_CONNECTED&&now-lastWiFi>9000){lastWiFi=now;WiFi.reconnect();}
 if(WiFi.status()==WL_CONNECTED&&!portal){
  if(ROLE_RING){
   bool down=digitalRead(RING_PIN)==LOW;
   if(down&&!wasDown)buttonAt=now;
   if(down&&buttonAt&&now-buttonAt>65&&now-lastPress>3500){
    lastPress=now;buttonAt=0;sendRing();
   }
   if(!down)buttonAt=0;
   wasDown=down;
  }else{
   receiveRing();
   if(!cloudURL.isEmpty()&&now-cloudPollAt>2200){cloudPollAt=now;pollCloud();}
   if(ringing&&digitalRead(SILENCE_PIN)==LOW)silence();
   if(ringing){
    if(now-ringAt>=30000)silence();
    else digitalWrite(BUZZER_PIN,((now-ringAt)%900)<550?HIGH:LOW);
   }
  }
 }
 delay(5);
}
