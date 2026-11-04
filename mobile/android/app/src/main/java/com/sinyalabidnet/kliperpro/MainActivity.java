package com.sinyalabidnet.kliperpro;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public class MainActivity extends Activity {
    private static final String PREFS = "skp";
    private static final String KEY_SERVER = "server_url";
    private static final int FILE_CHOOSER_REQUEST = 1001;

    private WebView webView;
    private ProgressBar progressBar;
    private SharedPreferences prefs;
    private ValueCallback<Uri[]> filePathCallback;
    private final Map<String, DownloadSession> downloadSessions = new HashMap<>();

    private static final String DOWNLOAD_PATCH_JS =
            "(function(){" +
            "if(window.__skpDownloadPatched)return;" +
            "window.__skpDownloadPatched=true;" +
            "try{" +
            "if(!navigator.clipboard||!navigator.clipboard.writeText){" +
            "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{" +
            "writeText:function(text){if(window.SKPDownloader){window.SKPDownloader.copyText(String(text));return Promise.resolve();}return Promise.reject(new Error('no clipboard'));}" +
            "}});" +
            "}" +
            "}catch(e){}" +
            "var orig=HTMLAnchorElement.prototype.click;" +
            "HTMLAnchorElement.prototype.click=function(){" +
            "var anchor=this;" +
            "try{" +
            "var href=this.href||'';" +
            "var name=this.download||'download';" +
            "if(href.indexOf('data:')===0){" +
            "if(window.SKPDownloader){window.SKPDownloader.downloadDataUrl(name,href);return;}" +
            "}" +
            "if(href.indexOf('blob:')===0){" +
            "if(!window.SKPDownloader){return orig.call(anchor);}" +
            "fetch(href).then(function(r){return r.blob();}).then(function(blob){" +
            "var id='skp_'+Date.now()+'_'+Math.random().toString(36).slice(2);" +
            "window.SKPDownloader.beginDownload(id,name,blob.type||'application/octet-stream',blob.size);" +
            "return blob.arrayBuffer().then(function(buffer){" +
            "var bytes=new Uint8Array(buffer);" +
            "var chunkSize=262144;" +
            "for(var offset=0;offset<bytes.length;offset+=chunkSize){" +
            "var end=Math.min(offset+chunkSize,bytes.length);" +
            "var binary='';" +
            "for(var i=offset;i<end;i++){binary+=String.fromCharCode(bytes[i]);}" +
            "window.SKPDownloader.appendDownloadChunk(id,btoa(binary));" +
            "}" +
            "window.SKPDownloader.finishDownload(id);" +
            "});" +
            "}).catch(function(){orig.call(anchor);});" +
            "return;" +
            "}" +
            "}catch(e){}" +
            "return orig.call(anchor);" +
            "};" +
            "})();";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P
                && checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.WRITE_EXTERNAL_STORAGE}, 2001);
        }

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0B1020"));

        webView = new WebView(this);
        configureWebView();

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setVisibility(View.GONE);

        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                Math.max(3, (int) (3 * getResources().getDisplayMetrics().density)));
        progressParams.gravity = Gravity.TOP;
        root.addView(progressBar, progressParams);

        setContentView(root);

        String saved = prefs.getString(KEY_SERVER, "");
        if (saved == null || saved.trim().isEmpty()) {
            showEmptyState();
            showServerDialog();
        } else {
            loadServer(saved);
        }
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setUserAgentString(settings.getUserAgentString() + " SinyalAbidnetKliperPro/1.0.3");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.addJavascriptInterface(new DownloadBridge(), "SKPDownloader");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(request.getUrl().toString());
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                view.evaluateJavascript(DOWNLOAD_PATCH_JS, null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    Toast.makeText(MainActivity.this, R.string.load_error, Toast.LENGTH_LONG).show();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                if (newProgress >= 100) {
                    progressBar.setVisibility(View.GONE);
                } else {
                    progressBar.setVisibility(View.VISIBLE);
                    progressBar.setProgress(newProgress);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(intent, "Pilih file"), FILE_CHOOSER_REQUEST);
                } catch (Exception e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "Tidak ada aplikasi file picker", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition,
                                        String mimeType, long contentLength) {
                enqueueDownload(url, userAgent, contentDisposition, mimeType);
            }
        });

        // Long-press anywhere on the page to change the server address.
        webView.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                showServerDialog();
                return true;
            }
        });
    }

    private void enqueueDownload(String url, String userAgent, String contentDisposition, String mimeType) {
        try {
            String fileName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setMimeType(mimeType);
            request.addRequestHeader("User-Agent", userAgent);
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) {
                request.addRequestHeader("Cookie", cookie);
            }
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setTitle(fileName);
            request.allowScanningByMediaScanner();

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                        "SinyalAbidnet Kliper Pro/" + fileName);
            } else {
                request.setDestinationInExternalFilesDir(MainActivity.this,
                        Environment.DIRECTORY_DOWNLOADS, fileName);
            }

            DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            if (dm != null) {
                dm.enqueue(request);
                Toast.makeText(MainActivity.this, R.string.download_started, Toast.LENGTH_SHORT).show();
            }
        } catch (Exception e) {
            Toast.makeText(MainActivity.this, "Gagal mengunduh: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private boolean handleUrl(String url) {
        if (url == null) return false;
        String lower = url.toLowerCase(Locale.ROOT);
        if (lower.startsWith("blob:") || lower.startsWith("data:") || lower.startsWith("javascript:")
                || lower.startsWith("about:") || lower.startsWith("file:") || lower.startsWith("content:")) {
            return false;
        }
        if (lower.startsWith("intent:")) {
            try {
                startActivity(Intent.parseUri(url, Intent.URI_INTENT_SCHEME));
            } catch (Exception ignored) {
            }
            return true;
        }
        if (lower.startsWith("mailto:") || lower.startsWith("tel:") || lower.startsWith("sms:")) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            } catch (Exception ignored) {
            }
            return true;
        }
        String serverHost = hostOf(prefs.getString(KEY_SERVER, ""));
        String targetHost = hostOf(url);
        if (serverHost != null && serverHost.equalsIgnoreCase(targetHost)) {
            return false;
        }
        if (lower.startsWith("http://") || lower.startsWith("https://")) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            } catch (Exception ignored) {
            }
            return true;
        }
        return false;
    }

    private String hostOf(String url) {
        try {
            return Uri.parse(url).getHost();
        } catch (Exception e) {
            return null;
        }
    }

    private String normalizeUrl(String raw) {
        if (raw == null) return null;
        String url = raw.trim();
        if (url.isEmpty()) return null;
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        while (url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        return url;
    }

    private void loadServer(String url) {
        String normalized = normalizeUrl(url);
        if (normalized == null) return;
        prefs.edit().putString(KEY_SERVER, normalized).apply();
        webView.loadUrl(normalized + "/");
    }

    private void showEmptyState() {
        String html = "<!doctype html><html><head>"
                + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>body{margin:0;background:#0b1020;color:#e5e7eb;"
                + "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
                + "display:flex;align-items:center;justify-content:center;height:100vh;"
                + "text-align:center;padding:24px;box-sizing:border-box}"
                + "div{max-width:420px}h1{font-size:20px;margin:0 0 10px}"
                + "p{color:#94a3b8;line-height:1.6;font-size:14px}"
                + "b{color:#c4b5fd}</style></head><body><div>"
                + "<h1>SinyalAbidnet Kliper Pro</h1>"
                + "<p>Server belum diatur.<br>Tekan lama layar ini atau buka menu "
                + "<b>&#8942; &rarr; Ganti Server</b> untuk memasukkan alamat server.</p>"
                + "</div></body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    private void showServerDialog() {
        final EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint(R.string.server_hint);
        input.setText(prefs.getString(KEY_SERVER, ""));
        input.setSelection(input.getText().length());
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        input.setPadding(pad, pad / 2, pad, pad / 2);

        AlertDialog.Builder builder = new AlertDialog.Builder(this)
                .setTitle(R.string.server_title)
                .setMessage(R.string.server_message)
                .setView(input)
                .setPositiveButton(R.string.server_save, null)
                .setNegativeButton(R.string.server_cancel, null);

        final AlertDialog dialog = builder.create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String normalized = normalizeUrl(input.getText().toString());
            if (normalized == null) {
                Toast.makeText(MainActivity.this, R.string.server_invalid, Toast.LENGTH_LONG).show();
                return;
            }
            testAndSave(dialog, normalized);
        }));
        dialog.show();
    }

    private void testAndSave(AlertDialog dialog, String url) {
        Toast.makeText(this, R.string.server_testing, Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            boolean ok = false;
            String error = "";
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(url + "/api/health").openConnection();
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setRequestMethod("GET");
                int code = conn.getResponseCode();
                if (code >= 200 && code < 400) {
                    java.io.BufferedReader reader = new java.io.BufferedReader(
                            new java.io.InputStreamReader(conn.getInputStream()));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    reader.close();
                    ok = sb.length() > 0;
                } else {
                    error = "HTTP " + code;
                }
                conn.disconnect();
            } catch (Exception e) {
                error = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            }

            final boolean success = ok;
            final String failure = error;
            runOnUiThread(() -> {
                if (success) {
                    dialog.dismiss();
                    loadServer(url);
                    Toast.makeText(MainActivity.this, R.string.server_ok, Toast.LENGTH_SHORT).show();
                } else {
                    new AlertDialog.Builder(MainActivity.this)
                            .setTitle(R.string.server_fail)
                            .setMessage("Detail: " + failure)
                            .setPositiveButton(R.string.server_retry, (d, w) -> testAndSave(dialog, url))
                            .setNeutralButton(R.string.server_save_anyway, (d, w) -> {
                                dialog.dismiss();
                                loadServer(url);
                            })
                            .setNegativeButton(R.string.server_cancel, null)
                            .show();
                }
            });
        }).start();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                }
            }
            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(results);
                filePathCallback = null;
            }
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, R.string.menu_change_server);
        menu.add(0, 2, 1, R.string.menu_reload);
        menu.add(0, 3, 2, R.string.menu_browser);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case 1:
                showServerDialog();
                return true;
            case 2:
                webView.reload();
                return true;
            case 3:
                String url = prefs.getString(KEY_SERVER, "");
                if (url != null && !url.isEmpty()) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    } catch (Exception ignored) {
                    }
                }
                return true;
            default:
                return super.onOptionsItemSelected(item);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private static class DownloadSession {
        File tempFile;
        FileOutputStream stream;
        String fileName;
        String mime;
    }

    private class DownloadBridge {
        @JavascriptInterface
        public void downloadDataUrl(String fileName, String dataUrl) {
            try {
                if (dataUrl == null || !dataUrl.startsWith("data:")) return;
                int comma = dataUrl.indexOf(',');
                if (comma < 0) return;
                String meta = dataUrl.substring(5, comma);
                String payload = dataUrl.substring(comma + 1);
                String mime = meta.split(";")[0];
                byte[] bytes;
                if (meta.contains(";base64")) {
                    bytes = Base64.decode(payload, Base64.DEFAULT);
                } else {
                    bytes = URLDecoder.decode(payload, "UTF-8").getBytes(StandardCharsets.UTF_8);
                }
                String saved = saveBytes(fileName, mime, bytes);
                final String message = saved != null ? "Tersimpan: " + saved : "Gagal menyimpan file";
                runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this,
                        "Gagal menyimpan: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }

        @JavascriptInterface
        public void beginDownload(String id, String fileName, String mime, long size) {
            try {
                File temp = new File(getCacheDir(), "skp_" + id + ".tmp");
                DownloadSession session = new DownloadSession();
                session.tempFile = temp;
                session.stream = new FileOutputStream(temp);
                session.fileName = fileName;
                session.mime = mime;
                downloadSessions.put(id, session);
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this,
                        "Gagal memulai unduhan: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }

        @JavascriptInterface
        public void appendDownloadChunk(String id, String base64) {
            DownloadSession session = downloadSessions.get(id);
            if (session == null) return;
            try {
                byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                session.stream.write(bytes);
            } catch (Exception e) {
                // finishDownload reports the final status.
            }
        }

        @JavascriptInterface
        public void finishDownload(String id) {
            DownloadSession session = downloadSessions.remove(id);
            if (session == null) return;
            try {
                session.stream.flush();
                session.stream.close();
                String saved = saveFileToDownloads(session.fileName, session.mime, session.tempFile);
                final String message = saved != null ? "Tersimpan: " + saved : "Gagal menyimpan file";
                runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this,
                        "Gagal menyimpan: " + e.getMessage(), Toast.LENGTH_LONG).show());
            } finally {
                if (session.tempFile != null) {
                    //noinspection ResultOfMethodCallIgnored
                    session.tempFile.delete();
                }
            }
        }

        @JavascriptInterface
        public void copyText(String text) {
            runOnUiThread(() -> {
                ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (clipboard != null) {
                    clipboard.setPrimaryClip(ClipData.newPlainText("SinyalAbidnet", text));
                }
            });
        }
    }

    private String saveBytes(String rawName, String mime, byte[] bytes) throws Exception {
        String fileName = sanitizeFileName(rawName);
        if (fileName.isEmpty()) {
            fileName = "sinyalabidnet-" + System.currentTimeMillis();
        }
        if (!fileName.contains(".")) {
            if ("application/json".equals(mime)) {
                fileName += ".json";
            } else if ("text/plain".equals(mime)) {
                fileName += ".txt";
            } else if ("video/mp4".equals(mime)) {
                fileName += ".mp4";
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE,
                    mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                    Environment.DIRECTORY_DOWNLOADS + "/SinyalAbidnet Kliper Pro");
            values.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) return null;
            try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                if (os == null) return null;
                os.write(bytes);
                os.flush();
            }
            values.clear();
            values.put(MediaStore.MediaColumns.IS_PENDING, 0);
            getContentResolver().update(uri, values, null, null);
            return "Downloads/SinyalAbidnet Kliper Pro/" + fileName;
        }

        boolean canPublic = checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
        File dir;
        if (canPublic) {
            dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                    "SinyalAbidnet Kliper Pro");
            if (!dir.exists() && !dir.mkdirs()) {
                dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                        "SinyalAbidnet Kliper Pro");
            }
        } else {
            dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                    "SinyalAbidnet Kliper Pro");
        }
        if (!dir.exists()) {
            dir.mkdirs();
        }
        File out = new File(dir, fileName);
        try (FileOutputStream fos = new FileOutputStream(out)) {
            fos.write(bytes);
        }
        return out.getAbsolutePath();
    }

    private String saveFileToDownloads(String rawName, String mime, File tempFile) throws Exception {
        String fileName = sanitizeFileName(rawName);
        if (fileName.isEmpty()) {
            fileName = "sinyalabidnet-" + System.currentTimeMillis();
        }
        if (!fileName.contains(".")) {
            if ("application/json".equals(mime)) {
                fileName += ".json";
            } else if ("text/plain".equals(mime)) {
                fileName += ".txt";
            } else if ("video/mp4".equals(mime)) {
                fileName += ".mp4";
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE,
                    mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                    Environment.DIRECTORY_DOWNLOADS + "/SinyalAbidnet Kliper Pro");
            values.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) return null;
            try (InputStream is = new FileInputStream(tempFile);
                 OutputStream os = getContentResolver().openOutputStream(uri)) {
                if (os == null) return null;
                byte[] buffer = new byte[64 * 1024];
                int len;
                while ((len = is.read(buffer)) > 0) {
                    os.write(buffer, 0, len);
                }
                os.flush();
            }
            values.clear();
            values.put(MediaStore.MediaColumns.IS_PENDING, 0);
            getContentResolver().update(uri, values, null, null);
            return "Downloads/SinyalAbidnet Kliper Pro/" + fileName;
        }

        boolean canPublic = checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
        File dir;
        if (canPublic) {
            dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
                    "SinyalAbidnet Kliper Pro");
            if (!dir.exists() && !dir.mkdirs()) {
                dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                        "SinyalAbidnet Kliper Pro");
            }
        } else {
            dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                    "SinyalAbidnet Kliper Pro");
        }
        if (!dir.exists()) {
            dir.mkdirs();
        }
        File out = new File(dir, fileName);
        try (InputStream is = new FileInputStream(tempFile);
             FileOutputStream fos = new FileOutputStream(out)) {
            byte[] buffer = new byte[64 * 1024];
            int len;
            while ((len = is.read(buffer)) > 0) {
                fos.write(buffer, 0, len);
            }
        }
        return out.getAbsolutePath();
    }

    private String sanitizeFileName(String name) {
        if (name == null) return "";
        String cleaned = name.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        int slash = Math.max(cleaned.lastIndexOf('/'), cleaned.lastIndexOf('\\'));
        if (slash >= 0) {
            cleaned = cleaned.substring(slash + 1);
        }
        return cleaned;
    }
}
