/* Password access for the encrypted Italy dataset. No password or key is stored here. */
(() => {
  'use strict';
  const form = document.getElementById('italy-access-form');
  if (!form) return;
  const field = document.getElementById('italy-password');
  const button = document.getElementById('italy-unlock');
  const status = document.getElementById('italy-unlock-status');
  const root = document.getElementById('italy-private-root');
  const toolbar = document.getElementById('italy-access-toolbar');
  const gate = document.getElementById('italy-access-gate');
  const downloadStatus = document.getElementById('italy-download-status');
  const base = new URL('assets/files/datasets/italy-protected/', document.baseURI);
  const encoder = new TextEncoder();
  const urls = new Set();
  const downloadBatchSize = 4;
  let key = null, config = null, vault = null, busyDownload = false;

  function fromBase64(text) {
    return Uint8Array.from(atob(text), c => c.charCodeAt(0));
  }
  function makeURL(blob) {
    const url = URL.createObjectURL(blob);
    urls.add(url);
    return url;
  }
  async function decryptPiece(name, expectedBytes) {
    if (!/^(vault|p_[a-f0-9]{24})\.bin$/.test(name)) throw new Error('Invalid resource');
    const response = await fetch(new URL(name, base), {cache: 'no-store', credentials: 'omit'});
    if (!response.ok) throw new Error('Resource unavailable');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 29 || (expectedBytes !== undefined && bytes.length !== expectedBytes)) {
      throw new Error('Incomplete resource');
    }
    return crypto.subtle.decrypt({name: 'AES-GCM', iv: bytes.subarray(0, 12),
      additionalData: encoder.encode(config.aadPrefix + name), tagLength: 128}, key, bytes.subarray(12));
  }
  async function unlock() {
    button.disabled = true;
    field.disabled = true;
    status.textContent = 'Checking password…';
    let authenticated = false;
    try {
      const response = await fetch(new URL('config.json', base), {cache: 'no-store', credentials: 'omit'});
      if (!response.ok) throw new Error('Access information unavailable');
      config = await response.json();
      if (config.version !== 1 || config.cipher !== 'AES-GCM' || config.compression !== 'gzip' ||
          config.manifest !== 'vault.bin' || config.aadPrefix !== 'adamdittrich-italy-v1/' ||
          config.kdf?.name !== 'PBKDF2' || config.kdf.hash !== 'SHA-256' ||
          !Number.isInteger(config.kdf.iterations) || config.kdf.iterations < 1000000 ||
          config.kdf.iterations > 2000000) throw new Error('Unsupported configuration');
      const salt = fromBase64(config.kdf.salt);
      if (salt.length !== 32) throw new Error('Unsupported salt');
      const passwordBytes = encoder.encode(field.value);
      let material;
      try {
        material = await crypto.subtle.importKey('raw', passwordBytes, 'PBKDF2', false, ['deriveKey']);
      } finally {
        passwordBytes.fill(0);
      }
      key = await crypto.subtle.deriveKey({name: 'PBKDF2', hash: 'SHA-256', salt,
        iterations: config.kdf.iterations}, material,
        {name: 'AES-GCM', length: 256}, false, ['decrypt']);
      const packed = await decryptPiece(config.manifest);
      authenticated = true;
      field.value = '';
      status.textContent = 'Opening the dataset…';
      const stream = new Blob([packed]).stream().pipeThrough(new DecompressionStream('gzip'));
      vault = JSON.parse(await new Response(stream).text());
      if (vault.version !== 1 || typeof vault.html !== 'string' || typeof vault.css !== 'string' ||
          typeof vault.script !== 'string' || !vault.downloads) throw new Error('Invalid portal');
      const style = document.createElement('style');
      style.id = 'italy-private-style';
      style.textContent = vault.css;
      document.head.append(style);
      root.innerHTML = vault.html;
      root.hidden = false;
      toolbar.hidden = false;
      gate.hidden = true;
      const script = document.createElement('script');
      script.id = 'italy-private-script';
      script.src = makeURL(new Blob([vault.script], {type: 'text/javascript'}));
      await new Promise((resolve, reject) => {
        script.addEventListener('load', resolve, {once: true});
        script.addEventListener('error', reject, {once: true});
        document.body.append(script);
      });
      status.textContent = '';
      document.getElementById('italy-lock').focus({preventScroll: true});
    } catch (error) {
      key = null;
      vault = null;
      urls.forEach(url => URL.revokeObjectURL(url));
      urls.clear();
      root.replaceChildren();
      root.hidden = true;
      toolbar.hidden = true;
      gate.hidden = false;
      document.getElementById('italy-private-style')?.remove();
      document.getElementById('italy-private-script')?.remove();
      status.textContent = !authenticated && error.name === 'OperationError'
        ? 'That password didn’t unlock the dataset. Please try again.'
        : 'The dataset could not be opened. Check your connection and try again.';
      field.disabled = false;
      button.disabled = false;
      field.focus();
      field.select();
    }
  }
  root.addEventListener('click', async event => {
    const control = event.target.closest('[data-asset]');
    if (!control || !root.contains(control)) return;
    event.preventDefault();
    const resource = vault?.downloads[control.dataset.asset];
    if (!resource || !key) return;
    if (busyDownload) {
      downloadStatus.textContent = 'Please wait for the current download.';
      return;
    }
    busyDownload = true;
    control.setAttribute('aria-disabled', 'true');
    try {
      if (!Array.isArray(resource.parts) || !resource.parts.length ||
          !Number.isSafeInteger(resource.size) || resource.size <= 0 ||
          !/^[a-f0-9]{64}$/.test(resource.sha256)) throw new Error('Invalid download');
      const buffers = new Array(resource.parts.length);
      let size = 0;
      downloadStatus.textContent = 'Preparing ' + resource.filename + '… 0%';
      // Four authenticated chunks at a time keeps large archives responsive
      // without making hundreds of simultaneous network requests.
      for (let offset = 0; offset < resource.parts.length; offset += downloadBatchSize) {
        const batch = resource.parts.slice(offset, offset + downloadBatchSize);
        const results = await Promise.allSettled(batch.map(async (part, index) => {
          if (!Number.isSafeInteger(part.bytes) || part.bytes < 29) throw new Error('Invalid part');
          const bytes = await decryptPiece(part.file, part.bytes);
          buffers[offset + index] = bytes;
          size += bytes.byteLength;
          if (size > resource.size) throw new Error('Invalid download size');
          downloadStatus.textContent = 'Preparing ' + resource.filename + '… ' +
            Math.round(size / resource.size * 100) + '%';
        }));
        const failed = results.find(result => result.status === 'rejected');
        if (failed) throw failed.reason;
      }
      if (size !== resource.size) throw new Error('Incomplete download');
      downloadStatus.textContent = 'Checking ' + resource.filename + '…';
      const blob = new Blob(buffers, {type: resource.mime});
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
      const hex = Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('');
      if (hex !== resource.sha256) throw new Error('Download integrity check failed');
      const url = makeURL(blob), save = document.createElement('a');
      save.href = url;
      save.download = resource.filename;
      save.hidden = true;
      document.body.append(save);
      save.click();
      save.remove();
      downloadStatus.textContent = resource.filename + ' is ready. Check your browser’s downloads.';
      setTimeout(() => { URL.revokeObjectURL(url); urls.delete(url); }, 120000);
    } catch (_) {
      downloadStatus.textContent = 'The download could not be prepared. Please try again.';
    } finally {
      busyDownload = false;
      control.removeAttribute('aria-disabled');
    }
  });
  document.getElementById('italy-lock').addEventListener('click', () => {
    key = null;
    vault = null;
    urls.forEach(url => URL.revokeObjectURL(url));
    location.replace(location.pathname);
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!button.disabled) unlock();
  });
  if (!window.isSecureContext || !window.crypto?.subtle || !window.DecompressionStream) {
    status.textContent = 'Please use a current browser to unlock the dataset.';
  } else button.disabled = false;
})();
