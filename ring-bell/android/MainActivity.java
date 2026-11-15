package in.gamesplanet.bell;
import android.app.*;
import android.os.*;
import android.Manifest;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.webkit.*;
import org.json.JSONObject;

public class MainActivity extends SessionActivity {
 private WebView web; private LanBridge lan; private UpdateChecker updater; private PermissionRequest pending; private AudioManager audio; private ToneGenerator tone; private Handler handler=new Handler(); private boolean ringing=false;
 private final Runnable repeat=new Runnable(){public void run(){if(!ringing)return; try{if(tone==null)tone=new ToneGenerator(AudioManager.STREAM_RING,85); tone.startTone(ToneGenerator.TONE_PROP_BEEP2,650);}catch(Exception e){} handler.postDelayed(this,1250);}};
 @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().addFlags(128);audio=(AudioManager)getSystemService(AUDIO_SERVICE);web=new WebView(this);setContentView(web);web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setMediaPlaybackRequiresUserGesture(false);web.addJavascriptInterface(new Bridge(),"BellNative");lan=new LanBridge(this);web.addJavascriptInterface(lan,"BellWifi");
 web.setWebViewClient(new WebViewClient(){
 @Override public boolean shouldOverrideUrlLoading(WebView v,String u){return !u.startsWith("https://appassets.androidplatform.net/");}
 @Override public WebResourceResponse shouldInterceptRequest(WebView v,WebResourceRequest r){String u=r.getUrl().toString();String root="https://appassets.androidplatform.net/";if(!u.startsWith(root))return null;String path=r.getUrl().getPath();if(path==null||path.contains(".."))return null;try{String n=path.substring(1);String type=n.endsWith(".html")?"text/html":n.endsWith(".js")?"application/javascript":n.endsWith(".png")?"image/png":"text/css";return new WebResourceResponse(type,n.endsWith(".png")?null:"UTF-8",getAssets().open(n));}catch(Exception e){return null;}}
 });
 web.setWebChromeClient(new WebChromeClient(){@Override public void onPermissionRequest(PermissionRequest r){runOnUiThread(()->{if(!isAppOrigin(r.getOrigin())){r.deny();return;}java.util.ArrayList<String> needs=new java.util.ArrayList<>();for(String x:r.getResources()){if(PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(x)){if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)needs.add(Manifest.permission.RECORD_AUDIO);}else if(PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(x)){if(checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED)needs.add(Manifest.permission.CAMERA);}else{r.deny();return;}}if(needs.isEmpty())r.grant(r.getResources());else{pending=r;requestPermissions(needs.toArray(new String[0]),101);}});}});
 web.loadUrl("https://appassets.androidplatform.net/"+BuildConfig.PAGE);
 }
 @Override public void onRequestPermissionsResult(int n,String[] p,int[] g){super.onRequestPermissionsResult(n,p,g);if(n==101&&pending!=null){boolean all=g.length>0;for(int x:g)if(x!=PackageManager.PERMISSION_GRANTED)all=false;if(all)pending.grant(pending.getResources());else pending.deny();pending=null;}}
 private static boolean isAppOrigin(android.net.Uri origin){
  return origin!=null&&"https".equalsIgnoreCase(origin.getScheme())&&"appassets.androidplatform.net".equalsIgnoreCase(origin.getHost())
      &&(origin.getPort()==-1||origin.getPort()==443);
 }
 void lanEvent(String event,String id,String payload){runOnUiThread(()->{if(allowed())web.evaluateJavascript("window.gpBellLanEvent&&window.gpBellLanEvent("+JSONObject.quote(event)+","+JSONObject.quote(id)+","+JSONObject.quote(payload)+")",null);});}
 private boolean allowed(){String u=web==null?null:web.getUrl();return u!=null&&u.startsWith("https://appassets.androidplatform.net/");}
 public class Bridge {
  @JavascriptInterface public void startRing(){runOnUiThread(()->{if(allowed()&&!ringing){ringing=true;handler.post(repeat);}});}
  @JavascriptInterface public void setSpeakerVolume(int value){runOnUiThread(()->{if(!allowed())return;try{int streamType=audio.getMode()==AudioManager.MODE_IN_COMMUNICATION?AudioManager.STREAM_VOICE_CALL:AudioManager.STREAM_MUSIC;int max=audio.getStreamMaxVolume(streamType);audio.setStreamVolume(streamType,Math.max(0,Math.min(max,(max*value)/100)),0);}catch(Exception e){}});}
  @JavascriptInterface public void stopRing(){runOnUiThread(()->stopTone());}
  @JavascriptInterface public void setCallAudio(boolean enabled){runOnUiThread(()->{if(!allowed())return;try{audio.setMode(enabled?AudioManager.MODE_IN_COMMUNICATION:AudioManager.MODE_NORMAL);audio.setSpeakerphoneOn(enabled);}catch(Exception e){}});}
 }
 private void stopTone(){ringing=false;handler.removeCallbacks(repeat);if(tone!=null){tone.release();tone=null;}}
 @Override protected void onResume(){super.onResume();if(updater==null)updater=new UpdateChecker(this);updater.resume();}
 @Override protected void onPause(){if(updater!=null)updater.pause();super.onPause();}
 @Override public void onDestroy(){stopTone();if(lan!=null)lan.shutdown();try{audio.setSpeakerphoneOn(false);audio.setMode(AudioManager.MODE_NORMAL);}catch(Exception e){} if(pending!=null)pending.deny();web.destroy();web=null;super.onDestroy();}
}
