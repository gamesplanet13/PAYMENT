package in.gamesplanet.tvpreview;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.content.Context;
import android.net.wifi.WifiManager;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebStorage;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.graphics.Color;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public class MainActivity extends Activity {
  private static final String PREVIEW="https://gamesplanet13.github.io/PAYMENT/preview.html";
  private static final int DISCOVERY_PORT=46822;
  private UpdateChecker updater;
  private WebView web; private Button retry; private volatile String projectionCode=""; private volatile boolean running=true; private DatagramSocket socket; private WifiManager.MulticastLock wifiLock;
  private class WifiBridge {
    @JavascriptInterface public void advertise(String code) { if(code!=null && code.matches("[0-9]{5}")) projectionCode=code; }
  }
  private void startDiscovery(){new Thread(()->{
    try {
      WifiManager wifi=(WifiManager)getApplicationContext().getSystemService(Context.WIFI_SERVICE);if(wifi!=null){wifiLock=wifi.createMulticastLock("gp-projection-discovery");wifiLock.setReferenceCounted(false);wifiLock.acquire();}
      socket=new DatagramSocket(null);socket.setReuseAddress(true);socket.setBroadcast(true);socket.bind(new InetSocketAddress(DISCOVERY_PORT));socket.setSoTimeout(1000);
      while(running){try{
        byte[] data=new byte[512];DatagramPacket request=new DatagramPacket(data,data.length);socket.receive(request);
        if(!"GP_PROJECTION_DISCOVER_V1".equals(new String(request.getData(),0,request.getLength(),StandardCharsets.UTF_8)) || projectionCode.isEmpty())continue;
        JSONObject reply=new JSONObject();reply.put("type","GP_PROJECTION_V1");reply.put("code",projectionCode);reply.put("name",Build.MODEL==null?"Android TV":Build.MODEL);
        byte[] out=reply.toString().getBytes(StandardCharsets.UTF_8);socket.send(new DatagramPacket(out,out.length,request.getAddress(),request.getPort()));
      }catch(java.net.SocketTimeoutException ignored){}catch(org.json.JSONException ignored){}}
    }catch(Exception ignored){}finally{if(socket!=null)socket.close();if(wifiLock!=null&&wifiLock.isHeld())wifiLock.release();}
  }).start();}
  @Override public void onCreate(Bundle state){super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    FrameLayout frame=new FrameLayout(this);web=new WebView(this);web.setBackgroundColor(Color.BLACK);web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setCacheMode(WebSettings.LOAD_NO_CACHE);
    web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.addJavascriptInterface(new WifiBridge(),"GPWifi");web.setFocusable(true);web.setFocusableInTouchMode(true);
    retry=new Button(this);retry.setText("Unable to open projection. Check internet and press OK to retry.");retry.setVisibility(View.GONE);
    retry.setOnClickListener(v->{retry.setVisibility(View.GONE);web.setVisibility(View.VISIBLE);web.loadUrl(PREVIEW);web.requestFocus();});
    web.setWebViewClient(new WebViewClient(){
      @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !"gamesplanet13.github.io".equalsIgnoreCase(request.getUrl().getHost());}
      @Override public void onReceivedError(WebView view,WebResourceRequest req,WebResourceError error){if(req.isForMainFrame()){web.setVisibility(View.GONE);retry.setVisibility(View.VISIBLE);retry.requestFocus();}}
    });
    frame.addView(web,new FrameLayout.LayoutParams(-1,-1));frame.addView(retry,new FrameLayout.LayoutParams(-1,-1));setContentView(frame);startDiscovery();resetAndOpen(PREVIEW);web.requestFocus();
  }
  @Override public boolean onKeyDown(int code,KeyEvent event){if(code==KeyEvent.KEYCODE_MENU||code==KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE){web.reload();return true;}return super.onKeyDown(code,event);}
  private void resetAndOpen(String url){
    web.clearCache(true); web.clearHistory(); web.clearFormData();
    WebStorage.getInstance().deleteAllData();
    CookieManager cookies=CookieManager.getInstance();
    cookies.removeAllCookies(value->{cookies.flush();if(web!=null&&!isFinishing())web.loadUrl(url);});
  }
  @Override protected void onResume(){super.onResume();if(updater==null)updater=new UpdateChecker(this);updater.start();}
  @Override protected void onDestroy(){running=false;if(socket!=null)socket.close();if(web!=null){web.removeJavascriptInterface("GPWifi");web.destroy();web=null;}super.onDestroy();}
}
