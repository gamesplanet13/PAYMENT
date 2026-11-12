package in.gamesplanet.qrcontrol;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebStorage;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public class MainActivity extends Activity {
  private static final String CONTROL = "https://gamesplanet13.github.io/PAYMENT/";
  private static final int DISCOVERY_PORT = 46822;
  private UpdateChecker updater;
  private WebView web;
  private Button retry;
  private volatile boolean scanning;
  private class WifiBridge {
    @JavascriptInterface public long getAppVersion() {
      try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionCode; }
      catch (Exception e) { return 0; }
    }
    @JavascriptInterface public void search() {
      synchronized (MainActivity.this) { if (scanning) return; scanning = true; }
      new Thread(() -> {
        try (DatagramSocket socket = new DatagramSocket()) {
          socket.setBroadcast(true);
          socket.setSoTimeout(700);
          byte[] msg = "GP_PROJECTION_DISCOVER_V1".getBytes(StandardCharsets.UTF_8);
          InetAddress broadcast = InetAddress.getByName("255.255.255.255");
          long end = System.currentTimeMillis() + 7000, next = 0;
          while (System.currentTimeMillis() < end && !isFinishing()) {
            if (System.currentTimeMillis() >= next) { socket.send(new DatagramPacket(msg,msg.length,broadcast,DISCOVERY_PORT)); next=System.currentTimeMillis()+1500; }
            try {
              byte[] buf = new byte[1024]; DatagramPacket packet = new DatagramPacket(buf,buf.length); socket.receive(packet);
              JSONObject reply = new JSONObject(new String(packet.getData(),0,packet.getLength(),StandardCharsets.UTF_8));
              String code = reply.optString("code", ""), name = reply.optString("name", "Projection");
              if (!code.matches("[0-9]{5}") || !"GP_PROJECTION_V1".equals(reply.optString("type"))) continue;
              if (name.length()>70) name=name.substring(0,70);
              final String script = "window.gpFoundProjection&&window.gpFoundProjection("+JSONObject.quote(code)+","+JSONObject.quote(name)+")";
              runOnUiThread(() -> { if (web != null) web.evaluateJavascript(script,null); });
            } catch (java.net.SocketTimeoutException ignored) {} catch (org.json.JSONException ignored) {}
          }
        } catch (Exception ignored) {} finally {
          scanning=false;
          runOnUiThread(() -> { if(web != null) web.evaluateJavascript("window.gpSearchFinished&&window.gpSearchFinished()",null); });
        }
      }).start();
    }
  }
  @Override public void onCreate(Bundle state) {
    super.onCreate(state); FrameLayout frame=new FrameLayout(this); web=new WebView(this);
    web.setBackgroundColor(Color.BLACK); web.getSettings().setJavaScriptEnabled(true); web.getSettings().setDomStorageEnabled(true);web.getSettings().setCacheMode(WebSettings.LOAD_NO_CACHE);
    web.getSettings().setAllowFileAccess(false); web.getSettings().setAllowContentAccess(false);
    web.addJavascriptInterface(new WifiBridge(),"GPWifi"); web.setWebChromeClient(new WebChromeClient()); retry=new Button(this);
    retry.setText("Unable to open control page. Check internet and tap to retry."); retry.setVisibility(View.GONE);
    retry.setOnClickListener(v->{retry.setVisibility(View.GONE);web.setVisibility(View.VISIBLE);web.loadUrl(CONTROL);});
    web.setWebViewClient(new WebViewClient(){
      @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !"gamesplanet13.github.io".equalsIgnoreCase(request.getUrl().getHost());}
      @Override public void onReceivedError(WebView view,WebResourceRequest req,WebResourceError error){if(req.isForMainFrame()){web.setVisibility(View.GONE);retry.setVisibility(View.VISIBLE);}}
    });
    frame.addView(web,new FrameLayout.LayoutParams(-1,-1));frame.addView(retry,new FrameLayout.LayoutParams(-1,-1));setContentView(frame);resetAndOpen(CONTROL);
  }
  @Override public void onBackPressed(){if(web!=null&&web.canGoBack())web.goBack();else super.onBackPressed();}
  private void resetAndOpen(String url){
    web.clearCache(true); web.clearHistory(); web.clearFormData();
    WebStorage.getInstance().deleteAllData();
    CookieManager cookies=CookieManager.getInstance();
    cookies.removeAllCookies(value->{cookies.flush();if(web!=null&&!isFinishing())web.loadUrl(url);});
  }
  @Override protected void onResume(){super.onResume();if(updater==null)updater=new UpdateChecker(this);updater.start();}
  @Override protected void onDestroy(){if(web!=null){web.removeJavascriptInterface("GPWifi");web.destroy();web=null;}super.onDestroy();}
}
