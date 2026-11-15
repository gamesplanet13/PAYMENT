#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
bt="${RING_BUILD_TOOLS:-$sdk/build-tools/35.0.0}"
platform="${RING_ANDROID_JAR:-$sdk/platforms/android-35/android.jar}"
: "${RING_SIGNING_KEY:?Set the existing Ring/Bell keystore path}"
: "${RING_SIGNING_PASSWORD_FILE:?Set the path to its password file}"
: "${RING_OUTPUT:?Set an output directory}"
mkdir -p "$RING_OUTPUT"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/assets" "$work/res/drawable-nodpi"
cp "$root"/{bell.html,ring.html,bell.js,lan-peer.js,gurbani-peer-manager.js,peerjs-1.5.5.min.js,PEERJS-LICENSE.txt,style.css,icon_ring.png,icon_bell.png} "$work/assets/"
cp "$root"/icon_{ring,bell}.png "$work/res/drawable-nodpi/"
sed -i 's|<nav aria-label="Ring और Bell">.*</nav>||' "$work/assets/"{ring,bell}.html
"$bt/aapt2" compile --dir "$work/res" -o "$work/res.zip"

for role in ring bell; do
  label="${role^}"
  role_dir="$work/$role"
  mkdir -p "$role_dir/classes" "$role_dir/dex"
  cat >"$role_dir/AndroidManifest.xml" <<MANIFEST
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="in.gamesplanet.doorbell.$role" android:versionCode="7" android:versionName="7.0">
    <uses-sdk android:minSdkVersion="23" android:targetSdkVersion="35"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE"/>
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE"/>
    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE"/>
    <uses-permission android:name="android.permission.RECORD_AUDIO"/>
    <uses-permission android:name="android.permission.CAMERA"/>
    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS"/>
    <uses-feature android:name="android.hardware.microphone" android:required="false"/>
    <uses-feature android:name="android.hardware.camera" android:required="false"/>
    <application android:enableOnBackInvokedCallback="false" android:icon="@drawable/icon_$role" android:label="Games Planet $label"
        android:theme="@android:style/Theme.Material.Light.NoActionBar" android:usesCleartextTraffic="false">
        <service android:name="in.gamesplanet.bell.SessionService" android:exported="false" android:foregroundServiceType="specialUse">
            <property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="Keep a user-started live local projection or doorbell connection available while switching apps"/>
        </service>
        <activity android:name="in.gamesplanet.bell.MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
MANIFEST
  printf 'package in.gamesplanet.bell; public final class BuildConfig { public static final String PAGE="%s.html"; }\n' "$role" >"$role_dir/BuildConfig.java"
  "$bt/aapt2" link -I "$platform" --manifest "$role_dir/AndroidManifest.xml" -A "$work/assets" \
    --auto-add-overlay -R "$work/res.zip" -o "$role_dir/base.apk"
  sources=("$root/android/"*.java "$role_dir/BuildConfig.java")
  if [[ -n "${RING_ECJ_JAR:-}" ]]; then
    java -jar "$RING_ECJ_JAR" -source 8 -target 8 -classpath "$platform" -d "$role_dir/classes" "${sources[@]}"
  else
    javac --release 8 -classpath "$platform" -d "$role_dir/classes" "${sources[@]}"
  fi
  "$bt/d8" --min-api 23 --lib "$platform" --output "$role_dir/dex" "$role_dir/classes/in/gamesplanet/bell/"*.class
  (cd "$role_dir/dex" && zip -q "$role_dir/base.apk" classes.dex)
  "$bt/zipalign" -f 4 "$role_dir/base.apk" "$role_dir/aligned.apk"
  apk="$RING_OUTPUT/Games_Planet_${label}_v7.apk"
  "$bt/apksigner" sign --ks "$RING_SIGNING_KEY" --ks-key-alias ringbell \
    --ks-pass "file:$RING_SIGNING_PASSWORD_FILE" --out "$apk" "$role_dir/aligned.apk"
  "$bt/apksigner" verify "$apk"
done
