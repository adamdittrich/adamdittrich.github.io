/* Password access for the encrypted Romania dataset. No password or key is stored here. */
(() => {
  'use strict';
  const form = document.getElementById('romania-access-form');
  if (!form) return;
  const field = document.getElementById('romania-password');
  const button = document.getElementById('romania-unlock');
  const status = document.getElementById('romania-unlock-status');
  const root = document.getElementById('romania-private-root');
  const toolbar = document.getElementById('romania-access-toolbar');
  const gate = document.getElementById('romania-access-gate');
  const downloadStatus = document.getElementById('romania-download-status');
  const base = new URL('assets/files/datasets/romania-protected/', document.baseURI);
  const encoder = new TextEncoder(), decoder = new TextDecoder();
  const urls = new Set();
  let key = null, config = null, vault = null, busyDownload = false;

  function fromBase64(text) {
    return Uint8Array.from(atob(text), c => c.charCodeAt(0));
  }
  function makeURL(blob) {
    const url = URL.createObjectURL(blob); urls.add(url); return url;
  }
  async function decryptPiece(name) {
    if (!/^(vault|p_[a-f0-9]{24})\.bin$/.test(name)) throw new Error('Invalid resource');
    const response = await fetch(new URL(name, base), {cache: 'no-store', credentials: 'omit'});
    if (!response.ok) throw new Error('Resource unavailable');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 29) throw new Error('Incomplete resource');
    return crypto.subtle.decrypt({name: 'AES-GCM', iv: bytes.subarray(0, 12),
      additionalData: encoder.encode(config.aadPrefix + name), tagLength: 128}, key, bytes.subarray(12));
  }
  async function unlock() {
    button.disabled = true; field.disabled = true;
    status.textContent = 'Checking password…';
    let authenticated = false;
    try {
      const response = await fetch(new URL('config.json', base), {cache: 'no-store', credentials: 'omit'});
      if (!response.ok) throw new Error('Access information unavailable');
      config = await response.json();
      if (config.version !== 1 || config.cipher !== 'AES-GCM' || config.compression !== 'gzip' ||
          config.kdf.name !== 'PBKDF2' || config.kdf.hash !== 'SHA-256' ||
          config.kdf.iterations < 100000 || config.kdf.iterations > 2000000) throw new Error('Unsupported configuration');
      const passwordBytes = encoder.encode(field.value);
      const material = await crypto.subtle.importKey('raw', passwordBytes, 'PBKDF2', false, ['deriveKey']);
      passwordBytes.fill(0);
      key = await crypto.subtle.deriveKey({name: 'PBKDF2', hash: 'SHA-256',
        salt: fromBase64(config.kdf.salt), iterations: config.kdf.iterations}, material,
        {name: 'AES-GCM', length: 256}, false, ['decrypt']);
      const packed = await decryptPiece(config.manifest);
      authenticated = true; field.value = '';
      status.textContent = 'Opening the dataset…';
      const stream = new Blob([packed]).stream().pipeThrough(new DecompressionStream('gzip'));
      vault = JSON.parse(await new Response(stream).text());
      const style = document.createElement('style');
      style.id = 'romania-private-style'; style.textContent = vault.css; document.head.append(style);
      root.innerHTML = vault.html;
      const script = document.createElement('script');
      script.src = makeURL(new Blob([vault.script], {type: 'text/javascript'}));
      script.addEventListener('error', () => { downloadStatus.textContent = 'The explorer could not start. Reload and try again.'; });
      document.body.append(script);
      root.hidden = false; toolbar.hidden = false; gate.hidden = true; status.textContent = '';
      document.getElementById('romania-lock').focus({preventScroll: true});
    } catch (error) {
      key = null; vault = null;
      urls.forEach(url => URL.revokeObjectURL(url)); urls.clear();
      root.replaceChildren(); root.hidden = true; toolbar.hidden = true; gate.hidden = false;
      document.getElementById('romania-private-style')?.remove();
      status.textContent = !authenticated && error.name === 'OperationError'
        ? 'That password didn’t unlock the dataset. Please try again.'
        : 'The dataset could not be opened. Check your connection and try again.';
      field.disabled = false; button.disabled = false; field.focus(); field.select();
    }
  }
  root.addEventListener('click', async event => {
    const control = event.target.closest('[data-asset]');
    if (!control || !root.contains(control)) return;
    event.preventDefault();
    const resource = vault?.downloads[control.dataset.asset];
    if (!resource || !key) return;
    if (busyDownload) { downloadStatus.textContent = 'Please wait for the current download.'; return; }
    busyDownload = true; control.setAttribute('aria-disabled', 'true');
    try {
      const buffers = []; let size = 0;
      for (const part of resource.parts) {
        const bytes = await decryptPiece(part.file); buffers.push(bytes); size += bytes.byteLength;
        downloadStatus.textContent = 'Preparing ' + resource.filename + '… ' + Math.round(size / resource.size * 100) + '%';
      }
      if (size !== resource.size) throw new Error('Incomplete download');
      const blob = new Blob(buffers, {type: resource.mime});
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
      const hex = Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('');
      if (hex !== resource.sha256) throw new Error('Download integrity check failed');
      const url = makeURL(blob), save = document.createElement('a');
      save.href = url; save.download = resource.filename; save.hidden = true;
      document.body.append(save); save.click(); save.remove();
      downloadStatus.textContent = resource.filename + ' is ready. Check your browser’s downloads.';
      setTimeout(() => { URL.revokeObjectURL(url); urls.delete(url); }, 120000);
    } catch (_) { downloadStatus.textContent = 'The download could not be prepared. Please try again.'; }
    finally { busyDownload = false; control.removeAttribute('aria-disabled'); }
  });
  document.getElementById('romania-lock').addEventListener('click', () => {
    key = null; vault = null; urls.forEach(url => URL.revokeObjectURL(url)); location.replace(location.pathname);
  });
  form.addEventListener('submit', event => { event.preventDefault(); if (!button.disabled) unlock(); });
  if (!window.isSecureContext || !window.crypto?.subtle || !window.DecompressionStream) {
    status.textContent = 'Please use a current browser to unlock the dataset.';
  } else button.disabled = false;
})();
