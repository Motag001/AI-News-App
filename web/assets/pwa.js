/* Install support: registers the service worker, offers an "Install app" button, shows an offline notice. */
(function () {
  "use strict";

  var secure = location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1";
  if ("serviceWorker" in navigator && secure) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () { /* the site works without it */ });
    });
  }

  var deferredPrompt = null;
  var button = null;

  function setInstallVisible(visible) {
    button = button || document.getElementById("install-app");
    if (button) button.hidden = !visible;
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault(); // keep the event so the install can start from our own button
    deferredPrompt = event;
    setInstallVisible(true);
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    setInstallVisible(false);
  });

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || target.id !== "install-app" || !deferredPrompt) return;
    var promptEvent = deferredPrompt;
    deferredPrompt = null;
    setInstallVisible(false);
    promptEvent.prompt();
  });

  // Running as an installed app: the install button is not needed.
  if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) setInstallVisible(false);

  function updateOnlineState() {
    var banner = document.getElementById("offline-banner");
    if (banner) banner.hidden = navigator.onLine;
  }
  window.addEventListener("online", updateOnlineState);
  window.addEventListener("offline", updateOnlineState);
  document.addEventListener("DOMContentLoaded", updateOnlineState);
})();
