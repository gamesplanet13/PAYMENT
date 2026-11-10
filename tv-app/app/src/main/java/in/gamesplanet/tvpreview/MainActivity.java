package in.gamesplanet.tvpreview;

import android.app.Activity;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.graphics.Color;

public class MainActivity extends Activity {
  private static final String PREVIEW = "https://gamesplanet13.github.io/PAYMENT/preview.html";
  private WebView web;
  private Button retry;
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    FrameLayout frame = new FrameLayout(this);
    web = new WebView(this);
    web.setBackgroundColor(Color.rgb(11,16,32));
    web.getSettings().setJavaScriptEnabled(true);
    web.getSettings().setDomStorageEnabled(true);
    web.getSettings().setAllowFileAccess(false);
    web.getSettings().setAllowContentAccess(false);
    web.setFocusable(true);
    web.setFocusableInTouchMode(true);
    retry = new Button(this);
    retry.setText("Unable to open preview. Check internet and press OK to retry.");
    retry.setVisibility(View.GONE);
    retry.setOnClickListener(v -> {retry.setVisibility(View.GONE); web.setVisibility(View.VISIBLE); web.loadUrl(PREVIEW); web.requestFocus();});
    web.setWebViewClient(new WebViewClient() {
      @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        String host = request.getUrl().getHost();
        return !"gamesplanet13.github.io".equalsIgnoreCase(host);
      }
      @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError error) {
        if (req.isForMainFrame()) {web.setVisibility(View.GONE); retry.setVisibility(View.VISIBLE); retry.requestFocus();}
      }
    });
    frame.addView(web, new FrameLayout.LayoutParams(-1,-1));
    frame.addView(retry, new FrameLayout.LayoutParams(-1,-1));
    setContentView(frame);
    web.loadUrl(PREVIEW);
    web.requestFocus();
  }
  @Override public boolean onKeyDown(int code, KeyEvent event) {
    if (code == KeyEvent.KEYCODE_MENU || code == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) {web.reload(); return true;}
    return super.onKeyDown(code,event);
  }
  @Override protected void onDestroy() {if(web != null) {web.destroy(); web=null;} super.onDestroy();}
}
