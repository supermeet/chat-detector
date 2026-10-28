

(function(){
  const e = React.createElement;
  const WHOLE = /^\s*\{\{\s*([^{}]+?)\s*\}\}\s*$/;
  const HOLE = /\{\{\s*([^{}]+?)\s*\}\}/g;
  function lookup(path, scopes) {
    path = path.trim();
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (/^-?\d+(\.\d+)?$/.test(path)) return +path;
    const parts = path.split('.');
    for (let i = scopes.length - 1; i >= 0; i--) {
      const s = scopes[i];
      if (s != null && parts[0] in Object(s)) {
        let v = s;
        for (const p of parts) { if (v == null) return undefined; v = v[p]; }
        return v;
      }
    }
    return undefined;
  }
  function interp(str, scopes) { return str.replace(HOLE, (_, p) => { const v = lookup(p, scopes); return v == null ? '' : String(v); }); }
  function attrVal(v, scopes) { const m = v.match(WHOLE); if (m) return lookup(m[1], scopes); return v.indexOf('{{') >= 0 ? interp(v, scopes) : v; }
  function styleObj(s) {
    const o = {};
    s.split(';').forEach((d) => {
      const i = d.indexOf(':'); if (i < 0) return;
      let k = d.slice(0, i).trim(); const v = d.slice(i + 1).trim(); if (!k) return;
      if (!k.startsWith('--')) k = k.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      o[k] = v;
    });
    return o;
  }
  function propName(n) {
    if (n === 'class') return 'className';
    if (n === 'for') return 'htmlFor';
    if (/^(aria|data)-/.test(n)) return n;
    if (n.indexOf('-') >= 0) return n.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    if (n === 'readonly') return 'readOnly';
    if (n === 'tabindex') return 'tabIndex';
    return n;
  }
  function childArr(node, scopes) {
    const out = []; let i = 0;
    for (const c of node.childNodes) { const r = render(c, scopes, i++); if (r !== null && r !== undefined) out.push(r); }
    return out;
  }
  function render(node, scopes, key) {
    if (node.nodeType === 3) {
      const t = node.nodeValue;
      if (!t.trim() && t.indexOf('\n') >= 0) return null;
      return t.indexOf('{{') >= 0 ? interp(t, scopes) : t;
    }
    if (node.nodeType !== 1) return null;
    const tag = node.nodeName;
    if (tag === 'sc-if') return attrVal(node.getAttribute('value'), scopes) ? e(React.Fragment, { key }, ...childArr(node, scopes)) : null;
    if (tag === 'sc-for') {
      const list = attrVal(node.getAttribute('list'), scopes) || [];
      const as = node.getAttribute('as') || 'item';
      return e(React.Fragment, { key }, list.map((it, i) => e(React.Fragment, { key: i }, ...childArr(node, scopes.concat([{ [as]: it, $index: i }])))));
    }
    const props = { key };
    for (const a of Array.from(node.attributes)) {
      if (a.name === 'xmlns' || a.name.indexOf('xmlns:') === 0) continue;
      let v = attrVal(a.value, scopes);
      const n = propName(a.name);
      if (n === 'style' && typeof v === 'string') v = styleObj(v);
      if (v === undefined) continue;
      props[n] = v;
    }
    return e(tag, props, ...childArr(node, scopes));
  }
  window.DCMount = function (tplText, Component) {
    let src = tplText.replace(/<!--[\s\S]*?-->/g, '').replace(/<(input|img|br|hr)\b([^>]*?)\s*\/?>/g, '<$1$2/>');
    const doc = new DOMParser().parseFromString('<root>' + src + '</root>', 'application/xml');
    const err = doc.getElementsByTagName('parsererror')[0];
    if (err) { document.body.textContent = 'Template error: ' + err.textContent; return; }
    const root = doc.documentElement;
    Component.prototype.render = function () { return e(React.Fragment, null, ...childArr(root, [this.renderVals()])); };
    ReactDOM.createRoot(document.getElementById('app')).render(e(Component, {}));
  };
  window.DCLogic = React.Component;
})();

