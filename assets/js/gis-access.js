/* Encrypted GIS access. No password or decrypting key is stored in this file. */
(() => {
  'use strict';
  const form = document.getElementById('gis-access-form');
  if (!form) return;
  const field = document.getElementById('gis-password');
  const button = document.getElementById('gis-unlock');
  const status = document.getElementById('gis-unlock-status');
  const privateRoot = document.getElementById('gis-private-root');
  const toolbar = document.getElementById('gis-access-toolbar');
  const gate = document.getElementById('gis-access-gate');
  const downloadStatus = document.getElementById('gis-download-status');
  const sealedBase = new URL('assets/files/datasets/historical-gis-protected/', document.baseURI);
  const originalBase = new URL('assets/files/datasets/historical-gis/', document.baseURI);
  const protectedPrefix = 'assets/files/datasets/historical-gis/';
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const objectURLs = new Set();
  const assets = new Map();
  const reverseAssets = new Map();
  let key = null;
  let config = null;
  let vault = null;
  let busyDownload = false;

  function fromBase64(text) {
    const raw = atob(text), bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }
  function makeURL(blob) {
    const url = URL.createObjectURL(blob);
    objectURLs.add(url);
    return url;
  }
  function originalURL(path) {
    const raw = String(path || '');
    const base = raw.startsWith('assets/') || raw.startsWith('/') ? document.baseURI : originalBase;
    const url = new URL(raw, base);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported resource URL');
    return url;
  }
  function resourcePath(path) {
    const url = originalURL(path);
    return url.origin === location.origin ? decodeURIComponent(url.pathname).replace(/^\//, '') : null;
  }
  function assetURL(path) {
    const normalized = resourcePath(path);
    if (normalized && assets.has(normalized)) return assets.get(normalized);
    if (normalized?.startsWith(protectedPrefix) && !vault.downloads[normalized]) {
      return '#gis-file-unavailable';
    }
    return originalURL(path).href;
  }
  async function encryptedBytes(name) {
    if (!/^(vault|p_[a-f0-9]{24})\.bin$/.test(name)) throw new Error('Invalid encrypted resource');
    const response = await fetch(new URL(name, sealedBase), {cache:'no-store', credentials:'omit'});
    if (!response.ok) throw new Error('Resource unavailable (HTTP ' + response.status + ')');
    return new Uint8Array(await response.arrayBuffer());
  }
  async function decryptPiece(name, decryptKey) {
    const bytes = await encryptedBytes(name);
    if (bytes.length < 29) throw new Error('Incomplete encrypted resource');
    return crypto.subtle.decrypt({name:'AES-GCM', iv:bytes.subarray(0,12),
      additionalData:encoder.encode(config.aadPrefix + name), tagLength:128},
      decryptKey, bytes.subarray(12));
  }
  async function decryptResource(resource, progress) {
    const buffers = [];
    let size = 0;
    for (let i = 0; i < resource.parts.length; i++) {
      const part = resource.parts[i];
      const plain = await decryptPiece(part.file, key);
      size += plain.byteLength;
      buffers.push(plain);
      if (progress) progress(size, resource.size);
    }
    if (size !== resource.size) throw new Error('Incomplete download');
    return new Blob(buffers, {type:resource.mime || 'application/octet-stream'});
  }
  async function unlock() {
    button.disabled = true;
    field.disabled = true;
    status.textContent = 'Checking password…';
    let authenticated = false;
    try {
      const response = await fetch(new URL('config.json', sealedBase), {cache:'no-store', credentials:'omit'});
      if (!response.ok) throw new Error('Access information is unavailable');
      config = await response.json();
      if (config.version !== 1 || config.cipher !== 'AES-GCM' ||
          config.kdf.name !== 'PBKDF2' || config.kdf.hash !== 'SHA-256' ||
          config.kdf.iterations < 100000 || config.kdf.iterations > 2000000) {
        throw new Error('Unsupported access configuration');
      }
      const passwordBytes = encoder.encode(field.value);
      const material = await crypto.subtle.importKey('raw', passwordBytes, 'PBKDF2', false, ['deriveKey']);
      passwordBytes.fill(0);
      key = await crypto.subtle.deriveKey({name:'PBKDF2', hash:'SHA-256',
        salt:fromBase64(config.kdf.salt), iterations:config.kdf.iterations}, material,
        {name:'AES-GCM',length:256}, false, ['decrypt']);
      const plain = await decryptPiece(config.manifest, key);
      vault = JSON.parse(decoder.decode(plain));
      authenticated = true;
      field.value = '';
      status.textContent = 'Opening maps and documentation…';
      const packed = await decryptResource(vault.ui, (done,total) => {
        status.textContent = 'Opening maps and documentation… ' + Math.round(done/total*100) + '%';
      });
      const stream = packed.stream().pipeThrough(new DecompressionStream('gzip'));
      const entries = JSON.parse(await new Response(stream).text());
      for (const entry of entries) {
        const url = makeURL(new Blob([fromBase64(entry.base64)], {type:entry.mime}));
        assets.set(entry.path, url);
        reverseAssets.set(url, entry.path);
      }
      window.GISPrivate = Object.freeze({assetURL});
      const style = document.createElement('style');
      style.id = 'gis-private-style';
      style.textContent = vault.css;
      document.head.append(style);
      privateRoot.innerHTML = vault.html;
      for (const image of privateRoot.querySelectorAll('[data-private-src]')) {
        image.src = assetURL(image.getAttribute('data-private-src'));
        image.removeAttribute('data-private-src');
      }
      // Preserve original filenames when downloading a decrypted image or JSON.
      privateRoot.addEventListener('click', onProtectedLink, true);
      const script = document.createElement('script');
      script.src = makeURL(new Blob([vault.script], {type:'text/javascript'}));
      script.addEventListener('error', () => {
        downloadStatus.textContent = 'The interactive explorer could not start. Reload and try again.';
      });
      document.body.append(script);
      privateRoot.hidden = false;
      toolbar.hidden = false;
      gate.hidden = true;
      status.textContent = '';
      document.getElementById('gis-lock').focus({preventScroll:true});
    } catch (error) {
      key = null;
      vault = null;
      for (const url of objectURLs) URL.revokeObjectURL(url);
      objectURLs.clear(); assets.clear(); reverseAssets.clear();
      privateRoot.replaceChildren();
      privateRoot.hidden = true;
      toolbar.hidden = true;
      gate.hidden = false;
      document.getElementById('gis-private-style')?.remove();
      status.textContent = !authenticated && error.name === 'OperationError'
        ? 'That password didn’t unlock the dataset. Please try again.'
        : 'The protected dataset could not be opened. Check your connection and try again.';
      field.disabled = false;
      button.disabled = false;
      field.focus();
      field.select();
    }
  }
  async function onProtectedLink(event) {
    const anchor = event.target.closest('a');
    if (!anchor || !privateRoot.contains(anchor)) return;
    const href = anchor.getAttribute('href') || '';
    if (href.startsWith('blob:')) {
      if (anchor.hasAttribute('download') && reverseAssets.has(href)) {
        anchor.download = reverseAssets.get(href).split('/').pop();
      }
      return;
    }
    if (href === '#gis-file-unavailable') {
      event.preventDefault();
      downloadStatus.textContent = 'This file is included in the complete downloadable editions.';
      return;
    }
    if (!href || href.startsWith('#') || href.startsWith('mailto:')) return;
    let normalized;
    try { normalized = resourcePath(href); } catch (_) { return; }
    if (!normalized?.startsWith(protectedPrefix)) return;
    event.preventDefault();
    const resource = vault.downloads[normalized];
    if (!resource || !key) {
      downloadStatus.textContent = 'This file is included in the complete downloadable editions.';
      return;
    }
    if (busyDownload) {
      downloadStatus.textContent = 'Please wait for the current download to finish.';
      return;
    }
    busyDownload = true;
    const label = anchor.textContent;
    anchor.setAttribute('aria-disabled', 'true');
    try {
      const blob = await decryptResource(resource, (done,total) => {
        const message = 'Preparing ' + resource.filename + '… ' + Math.round(done/total*100) + '%';
        downloadStatus.textContent = message;
        anchor.textContent = 'Preparing… ' + Math.round(done/total*100) + '%';
      });
      const url = makeURL(blob);
      const save = document.createElement('a');
      save.href = url; save.download = resource.filename; save.hidden = true;
      document.body.append(save); save.click(); save.remove();
      downloadStatus.textContent = resource.filename + ' is ready. Check your browser’s downloads.';
      setTimeout(() => {URL.revokeObjectURL(url); objectURLs.delete(url);}, 120000);
    } catch (_) {
      downloadStatus.textContent = 'The download could not be prepared. Please try again.';
    } finally {
      busyDownload = false;
      anchor.textContent = label;
      anchor.removeAttribute('aria-disabled');
    }
  }
  document.getElementById('gis-lock').addEventListener('click', () => {
    key = null;
    for (const url of objectURLs) URL.revokeObjectURL(url);
    location.replace(location.pathname);
  });
  form.addEventListener('submit', event => {event.preventDefault(); if (!button.disabled) unlock();});
  if (!window.isSecureContext || !window.crypto?.subtle || !window.DecompressionStream) {
    status.textContent = 'Please open this page in a current browser to unlock the dataset.';
  } else button.disabled = false;
})();
