/* install-prompt.js - Cross-platform PWA install prompt for Gibushun
 * iOS: Manual instructions (Share → Add to Home Screen)
 * Android: Intercepts beforeinstallprompt for native prompt
 * Desktop: Shows install button in nav
 */

(function() {
  'use strict';

  var DISMISS_KEY = 'gibushun-install-dismissed';
  var deferredPrompt = null;

  function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function isAndroid() {
    return /Android/.test(navigator.userAgent);
  }

  function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;
  }

  function wasDismissed() {
    return localStorage.getItem(DISMISS_KEY) === 'true';
  }

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, 'true');
    var banner = document.getElementById('install-banner');
    if (banner) banner.remove();
  }

  function createBanner(content) {
    var banner = document.createElement('div');
    banner.id = 'install-banner';
    banner.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#0085A1;color:white;' +
      'padding:15px 20px;z-index:9997;direction:rtl;text-align:center;font-size:14px;' +
      'box-shadow:0 -2px 10px rgba(0,0,0,0.2);';
    banner.innerHTML = content;
    document.body.appendChild(banner);

    var closeBtn = banner.querySelector('.install-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function(e) {
        e.preventDefault();
        dismiss();
      });
    }

    return banner;
  }

  function showIOSBanner() {
    createBanner(
      '<div style="margin-bottom:8px"><strong>להגנה על הנתונים, הוסף למסך הבית</strong></div>' +
      '<div style="font-size:13px">לחץ על <span style="font-size:18px">⎙</span> (שיתוף) בתפריט הדפדפן, ואז בחר "הוסף למסך הבית"</div>' +
      '<a href="#" class="install-close" style="color:white;text-decoration:underline;display:inline-block;margin-top:8px;font-size:12px">הבנתי</a>'
    );
  }

  function showAndroidBanner() {
    var banner = createBanner(
      '<div style="display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap">' +
      '<span><strong>התקן את מימדיון</strong> לגישה מהירה ועבודה אופליין</span>' +
      '<button id="install-btn" style="background:white;color:#0085A1;border:none;padding:8px 16px;border-radius:4px;font-weight:bold;cursor:pointer">התקן</button>' +
      '<a href="#" class="install-close" style="color:white;text-decoration:underline;font-size:12px">לא עכשיו</a>' +
      '</div>'
    );

    var installBtn = banner.querySelector('#install-btn');
    if (installBtn && deferredPrompt) {
      installBtn.addEventListener('click', function() {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function(choice) {
          if (choice.outcome === 'accepted') {
            dismiss();
          }
          deferredPrompt = null;
        });
      });
    }
  }

  function showDesktopBanner() {
    var banner = createBanner(
      '<div style="display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap">' +
      '<span><strong>התקן את מימדיון</strong> לעבודה אופליין</span>' +
      '<button id="install-btn" style="background:white;color:#0085A1;border:none;padding:8px 16px;border-radius:4px;font-weight:bold;cursor:pointer">התקן</button>' +
      '<a href="#" class="install-close" style="color:white;text-decoration:underline;font-size:12px">לא עכשיו</a>' +
      '</div>'
    );

    var installBtn = banner.querySelector('#install-btn');
    if (installBtn && deferredPrompt) {
      installBtn.addEventListener('click', function() {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function(choice) {
          if (choice.outcome === 'accepted') {
            dismiss();
          }
          deferredPrompt = null;
        });
      });
    }
  }

  // ─── Capture beforeinstallprompt (Android/Desktop Chrome) ─────────────────
  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    deferredPrompt = e;

    // Show banner if not dismissed and not already installed
    if (!wasDismissed() && !isStandalone()) {
      setTimeout(function() {
        if (isAndroid()) {
          showAndroidBanner();
        } else {
          showDesktopBanner();
        }
      }, 3000);
    }
  });

  // ─── Show iOS banner on load ──────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    // Only show install banner if user is authenticated
    var logoutLink = document.getElementById('logout-link');
    if (!logoutLink) return;

    if (isStandalone() || wasDismissed()) return;

    if (isIOS()) {
      setTimeout(function() { showIOSBanner(); }, 3000);
    }
  });

  // ─── Hide banner when installed ───────────────────────────────────────────
  window.addEventListener('appinstalled', function() {
    dismiss();
    if (window.showOfflineToast) {
      window.showOfflineToast('מימדיון הותקנה בהצלחה!');
    }
  });

})();
