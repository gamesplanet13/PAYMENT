/*
 GAMES PLANET - standalone Wi-Fi BELL (no phone required).
 ESP32 DevKit V1 / WROOM-32. Arduino-ESP32 3.x.
 Active-high 3.3V-compatible buzzer MODULE:
       VCC -> 3V3, GND -> GND, IN -> GPIO25.
 Silence pushbutton (normally open): GPIO33 -> button -> GND.
 Setup reset pushbutton: GPIO26 -> button -> GND, hold 6 seconds.
 A naked high-current buzzer MUST use a suitable transistor/MOSFET driver;
 never connect mains or an inductive bell directly to GPIO.
 Deploy esp32-doorbell/cloudflare-worker.js and give both devices the same
 worker HTTPS URL + long random DEVICE_TOKEN. Requires Internet.
*/
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <esp_http_client.h>
#include <esp_crt_bundle.h>
#include <time.h>
#define BUZZER_PIN 25
#define SILENCE_PIN 33
#define CONFIG_PIN 26
WebServer page(80);
DNSServer dns;
Preferences prefs;
String ssid,pass,relay,token,seenId;
bool portal=false,initialRead=true,ringing=false;
unsigned long lastPoll=0,lastWifi=0,ringStarted=0,lastTone=0,configStarted=0;
const unsigned long ringDuration=30000;
String apName(){
 char buf[26];snprintf(buf,sizeof(buf),"GP-BELL-RX-%04X",(unsigned int)(ESP.getEfuseMac()&65535));
 return String(buf);
}
String escapeHtml(String v){
 v.replace("&","&amp;");v.replace("<","&lt;");v.replace(">","&gt;");
 v.replace("\"","&quot;");v.replace("'","&#39;");return v;
}
void readSettings(){
 prefs.begin("gp-bell-rx",true);
 ssid=prefs.getString("ssid","");pass=prefs.getString("pwd","");
 relay=prefs.getString("relay","");token=prefs.getString("token","");
 seenId=prefs.getString("seen","");
 prefs.end();
}
void silence(){
 ringing=false;
 digitalWrite(BUZZER_PIN,LOW);
}
void startRing(){
 ringing=true;ringStarted=millis();lastTone=0;
 Serial.println("INCOMING INTERNET DOORBELL!");
}
void setupPortal(){
 portal=true;silence();
 WiFi.mode(WIFI_AP_STA);
 WiFi.softAP(apName().c_str(),"GPBellSetup");
 dns.start(53,"*",WiFi.softAPIP());
 page.on("/",HTTP_GET,[](){
  String html=R"HTML(<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Games Planet Bell Receiver</title><style>body{font:16px system-ui;background:#131922;color:#f7f7f7;padding:20px;max-width:600px;margin:auto}
  label{display:block;margin:14px 0}input,select,button{width:100%;padding:11px;box-sizing:border-box;font:inherit;border-radius:7px}
  button{background:#f1c365;border:0;font-weight:700}</style></head><body>
  <h2>GAMES PLANET - BELL Receiver</h2><p>Choose 2.4 GHz Wi-Fi, enter SAME relay URL and secret as the RING device.</p>
  <form method="post" action="/save"><label>Nearby Wi-Fi<select name="ssid">)HTML";
  int count=WiFi.scanNetworks(false,true);
  for(int i=0;i<count&&i<35;i++){
   String x=WiFi.SSID(i);html+="<option value=\""+escapeHtml(x)+"\">"+escapeHtml(x)+" ("+String(WiFi.RSSI(i))+" dBm)</option>";
  }
  html+=R"HTML(</select></label>)HTML";
  html+="<label>Wi-Fi password<input type=\"password\" name=\"password\" maxlength=\"63\" value=\""+escapeHtml(pass)+"\"></label>";
  html+="<label>Cloud relay HTTPS URL<input type=\"url\" required name=\"relay\" value=\""+escapeHtml(relay)+"\"></label>";
  html+="<label>Shared Device Token (32+ characters)<input type=\"password\" required name=\"token\" minlength=\"32\" maxlength=\"128\" value=\""+escapeHtml(token)+"\"></label>";
  html+="<button>Save and Connect</button></form></body></html>";
  page.send(200,"text/html; charset=utf-8",html);
 });
 page.on("/save",HTTP_POST,[](){
  String w=page.arg("ssid"),p=page.arg("password"),r=page.arg("relay"),t=page.arg("token");
  r.trim();t.trim();while(r.endsWith("/"))r.remove(r.length()-1);
  if(w.length()<1||w.length()>32||r.length()>200||!r.startsWith("https://")||t.length()<32||t.length()>128){
   page.send(400,"text/plain","Invalid Wi-Fi, relay URL or token");return;
  }
  prefs.begin("gp-bell-rx",false);
  prefs.putString("ssid",w);prefs.putString("pwd",p);prefs.putString("relay",r);prefs.putString("token",t);
  prefs.end();
  page.send(200,"text/html","Saved. Reconnecting to Wi-Fi...");
  delay(700);ESP.restart();
 });
 page.onNotFound([](){page.sendHeader("Location","/",true);page.send(302,"text/plain","");});
 page.begin();
 Serial.println("Setup hotspot: "+apName()+" password GPBellSetup");
 Serial.println("Open http://192.168.4.1");
}
static esp_err_t onResponse(esp_http_client_event_t *evt){
 if(evt->event_id==HTTP_EVENT_ON_DATA&&evt->user_data&&evt->data&&evt->data_len>0){
  String* out=static_cast<String*>(evt->user_data);
  if(out->length()<4096)out->concat((const char*)evt->data,evt->data_len);
 }
 return ESP_OK;
}
bool getEvents(String& body){
 if(WiFi.status()!=WL_CONNECTED||!relay.startsWith("https://")||token.length()<32)return false;
 String endpoint=relay+"/events";
 esp_http_client_config_t cfg={};
 cfg.url=endpoint.c_str();
 cfg.crt_bundle_attach=esp_crt_bundle_attach;
 cfg.timeout_ms=6000;
 cfg.event_handler=onResponse;
 cfg.user_data=&body;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);
 if(!client)return false;
 String bearer="Bearer "+token;
 esp_http_client_set_header(client,"Authorization",bearer.c_str());
 esp_err_t err=esp_http_client_perform(client);
 int response=esp_http_client_get_status_code(client);
 esp_http_client_cleanup(client);
 return err==ESP_OK&&response==200;
}
String extractJSONId(const String& s){
 // Only read the event id from the authenticated JSON response.
 int ev=s.indexOf("\"event\"");
 if(ev<0||s.indexOf("null",ev)>=0&&s.indexOf('{',ev)<0)return "";
 int id=s.indexOf("\"id\"",ev);
 if(id<0)return "";
 int colon=s.indexOf(':',id);if(colon<0)return "";
 int start=s.indexOf('"',colon+1),stop=start<0?-1:s.indexOf('"',start+1);
 if(stop<0||stop-start>90)return "";
 return s.substring(start+1,stop);
}
void pollBell(){
 String body;
 if(!getEvents(body)){
  Serial.println("Doorbell relay unreachable; retrying.");
  return;
 }
 String id=extractJSONId(body);
 if(id.isEmpty())return;
 // The first poll after initial provisioning is baseline, not a stale ring.
 if(initialRead){
  initialRead=false;
  if(seenId.isEmpty()){
   seenId=id;
   prefs.begin("gp-bell-rx",false);
   prefs.putString("seen",seenId);
   prefs.end();
   return;
  }
 }
 if(id!=seenId){
  seenId=id;
  prefs.begin("gp-bell-rx",false);prefs.putString("seen",seenId);prefs.end();
  startRing();
 }
}
void setup(){
 Serial.begin(115200);
 pinMode(BUZZER_PIN,OUTPUT);digitalWrite(BUZZER_PIN,LOW);
 pinMode(SILENCE_PIN,INPUT_PULLUP);
 pinMode(CONFIG_PIN,INPUT_PULLUP);
 readSettings();
 if(ssid.isEmpty()||relay.isEmpty()||token.length()<32){setupPortal();return;}
 WiFi.mode(WIFI_STA);WiFi.begin(ssid.c_str(),pass.c_str());
 unsigned long begin=millis();
 while(WiFi.status()!=WL_CONNECTED&&millis()-begin<12000)delay(200);
 if(WiFi.status()!=WL_CONNECTED)setupPortal();
 else{configTime(0,0,"pool.ntp.org","time.cloudflare.com");Serial.println("Bell receiver Wi-Fi online");}
}
void loop(){
 unsigned long now=millis();
 if(portal){dns.processNextRequest();page.handleClient();}
 if(digitalRead(SILENCE_PIN)==LOW&&ringing)silence();
 if(digitalRead(CONFIG_PIN)==LOW){
  if(!configStarted)configStarted=now;
  if(now-configStarted>6000){prefs.begin("gp-bell-rx",false);prefs.clear();prefs.end();ESP.restart();}
 }else configStarted=0;
 if(ringing){
  if(now-ringStarted>=ringDuration){silence();}
  else{
   // Audible repeating pattern: 500ms ON, 350ms OFF.
   digitalWrite(BUZZER_PIN,((now-ringStarted)%850)<500?HIGH:LOW);
  }
 }
 if(!portal&&WiFi.status()!=WL_CONNECTED&&now-lastWifi>10000){
  lastWifi=now;WiFi.reconnect();
 }
 if(!portal&&WiFi.status()==WL_CONNECTED&&now-lastPoll>1500){
  lastPoll=now;pollBell();
 }
 delay(5);
}
