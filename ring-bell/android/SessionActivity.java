package in.gamesplanet.bell;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;

public abstract class SessionActivity extends Activity {
    private AlertDialog exitDialog;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        Intent service = new Intent(this, SessionService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service);
        else startService(service);
    }

    @Override public final void onBackPressed() {
        if (isFinishing() || (exitDialog != null && exitDialog.isShowing())) return;
        exitDialog = new AlertDialog.Builder(this)
            .setTitle("Exit")
            .setMessage("Close this app and end its active connections?")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Exit", (dialog, which) -> {
                stopService(new Intent(this, SessionService.class));
                finishAndRemoveTask();
            }).show();
    }
}
