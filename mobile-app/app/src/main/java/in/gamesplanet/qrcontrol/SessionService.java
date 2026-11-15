package in.gamesplanet.qrcontrol;

import android.app.*;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

public final class SessionService extends Service {
    private static final String CHANNEL = "active_session";

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(new NotificationChannel(
                CHANNEL, "Active connection", NotificationManager.IMPORTANCE_LOW));
        }
        Intent open = new Intent(this, MainActivity.class).addFlags(
            Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent show = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder notice = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        startForeground(1, notice.setContentTitle(getApplicationInfo().loadLabel(getPackageManager()))
            .setContentText("Connection session active. Open the app to exit.")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentIntent(show).setOngoing(true).build());
        return START_NOT_STICKY;
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onTaskRemoved(Intent rootIntent) {
        stopSelf();
        super.onTaskRemoved(rootIntent);
    }
}
