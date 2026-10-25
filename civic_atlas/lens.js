/* Universal opt-in Dais Lens. Captured pixels never leave this browser. */
(() => {
  const floating = $('#floating-lens');
  const home = $('#tiles-home');
  const floatingTiles = $('#floating-tiles');
  let capture = null;
  let popup = null;
  let floatingWanted = false;
  let sharingPending = false;
  let source = 'No video selected';
  let adjust = false;

  function updateStatus() {
    $('#capture-status').textContent = 'Source: ' + source + (capture ? ' · shared pixels stay in your browser; control playback in the original tab.' : '');
    $('#float-source').textContent = source;
    $('#stop-share').hidden = !capture;
    $('#float-stop').hidden = !capture;
    $('#share-video').disabled = sharingPending;
    $('#float-share').disabled = sharingPending;
    const target = popup && !popup.closed ? popup.document : null;
    if (target) {
      target.querySelector('#popup-source').textContent = source;
      target.querySelector('#popup-stop').hidden = !capture;
      target.querySelector('#popup-share').disabled = sharingPending;
    }
  }
  window.setLensSource = text => { source = text; updateStatus(); };

  function restoreTiles() {
    window.lensWindowOpen = false;
    popup = null;
    (floatingWanted ? floatingTiles : home).append(tilesContainer);
    floating.hidden = !floatingWanted;
    tilesContainer.classList.toggle('compact-tiles', floatingWanted && !adjust);
    $('#lens-toggle').setAttribute('aria-pressed', String(floatingWanted));
    drawTiles();
  }

  function showFloating(on) {
    floatingWanted = on;
    if (popup && !popup.closed) popup.close();
    restoreTiles();
  }

  function stopCapture(message) {
    const old = capture;
    capture = null;
    if (old) old.getTracks().forEach(track => track.stop());
    if (video.srcObject) {
      video.pause();
      video.srcObject = null;
      video.removeAttribute('src');
      video.load();
    }
    video.controls = true;
    video.muted = false;
    if (old) source = message || 'Sharing stopped · choose another source';
    updateStatus();
    drawTiles();
  }
  window.releaseLensCapture = () => stopCapture();

  async function shareVideo() {
    if (sharingPending) return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getDisplayMedia) {
      toast('Tab sharing needs a supported desktop browser over HTTPS. You can still use local videos.');
      return;
    }
    sharingPending = true;
    updateStatus();
    try {
      // User chooses the source explicitly. No background capture or remote fetching.
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 30, max: 30 } }, audio: false,
        selfBrowserSurface: 'exclude', surfaceSwitching: 'include'
      });
      stopCapture();
      capture = stream;
      video.pause();
      video.removeAttribute('src');
      video.srcObject = stream;
      video.muted = true;
      video.controls = false;
      source = 'Shared video tab / window';
      $('#video-select').value = '';
      stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        if (capture === stream) stopCapture('Sharing ended · choose another source');
      }));
      try { await video.play(); }
      catch (error) { stopCapture('Shared video could not start'); throw error; }
      if (!popup || popup.closed) showFloating(true);
      toast('Lens is on. Adjust crops to the visible dais; control playback in the shared tab.');
    } catch (error) {
      const denied = ['NotAllowedError', 'AbortError'].includes(error.name);
      toast(denied ? 'Sharing was cancelled or blocked. Open the preview in its own tab and try again.' : 'Could not share this source. Try another tab/window or a local video.');
    } finally {
      sharingPending = false;
      updateStatus();
    }
  }

  function toggleSettings() {
    adjust = !adjust;
    tilesContainer.classList.toggle('compact-tiles', !adjust);
    $('#float-settings').setAttribute('aria-pressed', String(adjust));
    if (popup && !popup.closed) popup.document.querySelector('#popup-settings').setAttribute('aria-pressed', String(adjust));
  }

  function popOut() {
    if (popup && !popup.closed) { popup.focus(); return; }
    const win = window.open('', 'civic-atlas-dais-lens', 'popup,width=650,height=850,resizable=yes,scrollbars=yes');
    if (!win) { showFloating(true); toast('Pop-up blocked. Allow pop-ups, or use the floating lens here.'); return; }
    popup = win;
    window.lensWindowOpen = true;
    floatingWanted = true;
    floating.hidden = true;
    $('#lens-toggle').setAttribute('aria-pressed', 'true');
    const doc = win.document;
    doc.title = 'Dais Lens · Any Video';
    doc.head.replaceChildren();
    const title = doc.createElement('title'); title.textContent = 'Dais Lens · Any Video'; doc.head.append(title);
    const css = doc.createElement('link'); css.rel = 'stylesheet'; css.href = new URL('/style.css', location.href).href; doc.head.append(css);
    doc.body.replaceChildren(); doc.body.className = 'lens-popup';
    const top = el('div', 'popup-heading');
    top.append(el('h2', '', '▣ Dais Lens'));
    const subtitle = el('p', '', source); subtitle.id = 'popup-source'; top.append(subtitle);
    const actions = el('div', 'float-actions');
    const actionsList = [
      ['popup-share', 'Share video tab', shareVideo],
      ['popup-settings', 'Adjust crops', toggleSettings],
      ['popup-save', 'Save layout', () => $('#save-layout').click()],
      ['popup-add', '＋ Seat', () => $('#add-tile').click()],
      ['popup-stop', 'Stop sharing', () => stopCapture()],
      ['popup-dock', 'Dock lens', () => showFloating(true)]
    ];
    actionsList.forEach(([id, label, action]) => {
      const button = el('button', '', label); button.id = id; button.onclick = action; actions.append(button);
    });
    top.append(actions); doc.body.append(top, tilesContainer);
    tilesContainer.classList.toggle('compact-tiles', !adjust);
    const note = el('p', 'float-help', 'Keep Civic Atlas open. Place this window beside any meeting player. Share that player’s tab/window to see its visible faces here. This is a separate window, not an always-on-top system overlay.');
    doc.body.append(note);
    win.addEventListener('pagehide', () => { if (popup === win) restoreTiles(); }, { once: true });
    updateStatus(); drawTiles(); win.focus();
  }

  $('#lens-toggle').onclick = () => showFloating(!floatingWanted);
  $('#float-close').onclick = () => showFloating(false);
  $('#share-video').onclick = shareVideo;
  $('#float-share').onclick = shareVideo;
  $('#stop-share').onclick = () => stopCapture();
  $('#float-stop').onclick = () => stopCapture();
  $('#float-settings').onclick = toggleSettings;
  $('#pop-lens').onclick = popOut;
  $('#float-pop').onclick = popOut;
  // Frame callbacks follow the single source even when the map is the selected view.
  if (video.requestVideoFrameCallback) {
    const next = () => { drawTiles(); video.requestVideoFrameCallback(next); };
    video.requestVideoFrameCallback(next);
  }
  window.addEventListener('beforeunload', () => {
    if (capture) capture.getTracks().forEach(track => track.stop());
    if (popup && !popup.closed) popup.close();
  });
  updateStatus();
})();
