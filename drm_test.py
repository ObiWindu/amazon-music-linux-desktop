
import os
import sys

cdm_path = "/var/lib/widevine/libwidevinecdm.so"

# Must be set before Qt WebEngine is initialized.
flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
flags += f" --widevine-cdm-path={cdm_path}"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView

HTML = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Widevine Diagnostic</title></head>
<body style="font: 16px sans-serif; padding: 24px">
<h2>Widevine compatibility test</h2>
<pre id="result">Checking browser support...</pre>
<script>
(async () => {
  const out = document.getElementById('result');
  out.textContent =
    'User agent: ' + navigator.userAgent + '\\n';

  if (!navigator.requestMediaKeySystemAccess) {
    out.textContent += 'EME API unavailable.';
    return;
  }

  try {
    const access = await navigator.requestMediaKeySystemAccess(
      'com.widevine.alpha',
      [{
        initDataTypes: ['cenc'],
        videoCapabilities: [{
          contentType: 'video/mp4; codecs="avc1.42E01E"',
          robustness: ''
        }]
      }]
    );
    out.textContent +=
      'Widevine key system available: ' + access.keySystem;
  } catch (e) {
    out.textContent +=
      'Widevine unavailable: ' + e.name + ': ' + e.message;
  }
})();
</script>
</body>
</html>
"""


app = QApplication(sys.argv)
window = QMainWindow()
window.setWindowTitle("Widevine Diagnostic")
window.resize(850, 500)

view = QWebEngineView()
window.setCentralWidget(view)
view.setHtml(HTML, QUrl("https://music.amazon.com/"))

window.show()
sys.exit(app.exec())
