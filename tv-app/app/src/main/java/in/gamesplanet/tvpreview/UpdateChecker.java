package in.gamesplanet.tvpreview;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import org.json.JSONObject;

/** Fetches update metadata off the UI thread and asks Android to install a verified download. */
final class UpdateChecker {
 private static final String BASE="https://gamesplanet13.github.io/PAYMENT/updates/";
 private static final String META=BASE+"projection.json";
 private final Activity activity; private final Handler ui=new Handler(Looper.getMainLooper());
 private final DownloadManager downloads; private final SharedPreferences prefs;
 private volatile boolean watching=false; private boolean dialogShowing=false;
 UpdateChecker(Activity a){activity=a;downloads=(DownloadManager)a.getSystemService(Context.DOWNLOAD_SERVICE);prefs=a.getSharedPreferences("app_updater",Context.MODE_PRIVATE);}
 void start(){try{long installed=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0).versionCode;if(prefs.getLong("version_code",0)<=installed&&prefs.getLong("download_id",-1)!=-1)prefs.edit().clear().apply();}catch(Exception ignored){}if(prefs.getLong("download_id",-1)!=-1)watch();else new Thread(this::check,"update-check").start();}
 private void check(){
  HttpURLConnection c=null;try{
   c=(HttpURLConnection)new URL(META+"?v="+System.currentTimeMillis()).openConnection();c.setConnectTimeout(10000);c.setReadTimeout(10000);c.setUseCaches(false);if(c.getResponseCode()!=200)return;
   byte[] bytes;try(InputStream in=c.getInputStream()){java.io.ByteArrayOutputStream b=new java.io.ByteArrayOutputStream();byte[] tmp=new byte[1024];int n;while((n=in.read(tmp))!=-1){if(b.size()+n>16384)return;b.write(tmp,0,n);}bytes=b.toByteArray();}
   JSONObject j=new JSONObject(new String(bytes,java.nio.charset.StandardCharsets.UTF_8));long latest=j.getLong("versionCode");long current=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0).versionCode;
   String url=j.getString("url"), hash=j.getString("sha256").toLowerCase(Locale.ROOT),version=j.getString("versionName");
   Uri u=Uri.parse(url);if(latest<=current||!url.startsWith(BASE)||!"https".equals(u.getScheme())||!"gamesplanet13.github.io".equals(u.getHost())||!hash.matches("[0-9a-f]{64}")||!url.endsWith(".apk"))return;
   String file="GamesPlanet-projection-"+latest+".apk";
   DownloadManager.Request request=new DownloadManager.Request(u).setTitle("Games Planet update "+version).setDescription("Update ready to install").setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED).setMimeType("application/vnd.android.package-archive").setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,file);
   long id=downloads.enqueue(request);prefs.edit().putLong("download_id",id).putString("hash",hash).putString("version",version).putLong("version_code",latest).apply();watch();
  }catch(Exception ignored){}finally{if(c!=null)c.disconnect();}
 }
 private void watch(){synchronized(this){if(watching)return;watching=true;}new Thread(()->{try{
  for(int i=0;i<360;i++){long id=prefs.getLong("download_id",-1);if(id<0)return;int status=-1;try(Cursor cur=downloads.query(new DownloadManager.Query().setFilterById(id))){if(cur!=null&&cur.moveToFirst())status=cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));}
   if(status==DownloadManager.STATUS_SUCCESSFUL){Uri uri=downloads.getUriForDownloadedFile(id);if(uri==null||!verify(uri,prefs.getString("hash",""))){downloads.remove(id);prefs.edit().clear().apply();return;}ui.post(()->prompt(uri));return;}
   if(status==DownloadManager.STATUS_FAILED){prefs.edit().clear().apply();return;}Thread.sleep(2000);
  }
 }catch(Exception ignored){}finally{watching=false;}},"update-download").start();}
 private boolean verify(Uri uri,String expected){try(InputStream in=activity.getContentResolver().openInputStream(uri)){if(in==null)return false;MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] buf=new byte[16384];int n;while((n=in.read(buf))!=-1)digest.update(buf,0,n);StringBuilder result=new StringBuilder();for(byte b:digest.digest())result.append(String.format(Locale.ROOT,"%02x",b&255));return result.toString().equals(expected);}catch(Exception e){return false;}}
 private void prompt(Uri uri){if(activity.isFinishing()||activity.isDestroyed()||dialogShowing)return;dialogShowing=true;new AlertDialog.Builder(activity).setTitle("Games Planet update ready").setMessage("Version "+prefs.getString("version","")+" has downloaded. Install it now?").setPositiveButton("Install",(d,w)->{dialogShowing=false;if(Build.VERSION.SDK_INT>=26&&!activity.getPackageManager().canRequestPackageInstalls()){Intent allow=new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName()));activity.startActivity(allow);return;}try{Intent install=new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);activity.startActivity(install);}catch(Exception ignored){}}).setNegativeButton("Later",(d,w)->dialogShowing=false).setOnCancelListener(d->dialogShowing=false).show();}
}
