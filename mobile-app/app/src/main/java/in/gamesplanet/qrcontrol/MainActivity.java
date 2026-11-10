package in.gamesplanet.qrcontrol;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.view.View;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;

public class MainActivity extends Activity {
  private static final String CONTROL = "https://gamesplanet13.github.io/PAYMENT/";
  private WebView web;
  private Button retry;
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    FrameLayout frame = new FrameLayout(this);
    web = new WebView(this);
    web.setBackgroundColor(Color.BLACK);
    web.getSettings().setJavaScriptEnabled(true);
    web.getSettings().setDomStorageEnabled(true);
    web.getSettings().setAllowFileAccess(false);
    web.getSettings().setAllowContentAccess(false);
    web.setWebChromeClient(new WebChromeClient());
    retry = new Button(this);
    retry.setText("Unable to open control page. Check internet and tap to retry.");
    retry.setVisibility(View.GONE);
    retry.setOnClickListener(v -> {retry.setVisibility(View.GONE); web.setVisibility(View.VISIBLE); web.loadUrl(CONTROL);});
    web.setWebViewClient(new WebViewClient() {
      @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        return !"gamesplanet13.github.io".equalsIgnoreCase(request.getUrl().getHost());
      }
      @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError error) {
        if (req.isForMainFrame()) {web.setVisibility(View.GONE); retry.setVisibility(View.VISIBLE);}
      }
    });
    frame.addView(web, new FrameLayout.LayoutParams(-1,-1));
    frame.addView(retry, new FrameLayout.LayoutParams(-1,-1));
    setContentView(frame);
    web.loadUrl(CONTROL);
  }
  @Override public void onBackPressed() {
    if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed();
  }
  @Override protected void onDestroy() {if(web != null) {web.destroy(); web=null;} super.onDestroy();}
}
