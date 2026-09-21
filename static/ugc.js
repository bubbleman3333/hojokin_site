// みんなの体験談（投稿・表示）。minna_api（Cloudflare Workers）を呼ぶ。
// <div id="ugc" data-api="…" data-site="hojokin" data-key="S-00000000"> に描画する。API に届かなければ何も出さない。
(function () {
  var root = document.getElementById('ugc');
  if (!root || !root.dataset.api) return;
  var API = root.dataset.api.replace(/\/$/, ''), SITE = root.dataset.site, KEY = root.dataset.key;
  var KIND_LABEL = { applied: '申請した', adopted: '採択された', rejected: '不採択だった', considering: '検討中' };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function stars(n) { return n ? '★'.repeat(n) + '☆'.repeat(5 - n) : ''; }
  function render(data) {
    var s = data.stats, html = '';
    html += '<h2>みんなの体験談</h2>';
    if (s.count) {
      html += '<div class="ugc-stats">' +
        '<span>投稿 ' + s.count + ' 件</span>' +
        (s.kinds.adopted || s.kinds.rejected ? '<span>採択 ' + (s.kinds.adopted || 0) + ' / 不採択 ' + (s.kinds.rejected || 0) + '</span>' : '') +
        (s.avg_rating ? '<span>申請しやすさ ' + s.avg_rating + ' / 5</span>' : '') + '</div>';
      html += '<ul class="ugc-list">' + data.posts.map(function (p) {
        return '<li><div class="ugc-head"><span class="badge ugc-' + esc(p.kind) + '">' + (KIND_LABEL[p.kind] || esc(p.kind)) + '</span> ' +
          (p.rating ? '<span class="ugc-stars">' + stars(p.rating) + '</span> ' : '') +
          '<span class="meta">' + esc(p.name || '匿名') + ' ・ ' + esc(p.created_at.slice(0, 10)) + '</span>' +
          '<button type="button" class="ugc-report" data-id="' + p.id + '" title="通報">通報</button></div>' +
          '<p>' + esc(p.body).replace(/\n/g, '<br>') + '</p></li>';
      }).join('') + '</ul>';
    } else {
      html += '<p class="small">まだ投稿はありません。申請した・検討している方の体験が、次に申請する人の助けになります。</p>';
    }
    html += '<form class="ugc-form" autocomplete="off">' +
      '<div class="ugc-row"><label>状況 <select name="kind">' + Object.keys(KIND_LABEL).map(function (k) { return '<option value="' + k + '">' + KIND_LABEL[k] + '</option>'; }).join('') + '</select></label>' +
      '<label>申請しやすさ <select name="rating"><option value="">未評価</option><option value="5">5 とても簡単</option><option value="4">4</option><option value="3">3 ふつう</option><option value="2">2</option><option value="1">1 とても大変</option></select></label>' +
      '<label>お名前（任意） <input name="name" maxlength="30" placeholder="匿名"></label></div>' +
      '<textarea name="body" maxlength="600" rows="4" placeholder="準備にかかった期間、つまずいた点、相談した窓口など。URL や連絡先は書けません（5〜600 字）"></textarea>' +
      '<input name="website" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px">' +
      '<div class="ugc-row"><button type="submit" class="button">体験を投稿する</button><span class="ugc-msg small"></span></div>' +
      '<p class="small">投稿は匿名で公開されます。個人や会社が特定される情報は書かないでください。不適切な投稿は通報 3 件で自動的に非表示になります。</p></form>';
    root.innerHTML = html;
    root.querySelector('.ugc-form').addEventListener('submit', submit);
    Array.prototype.forEach.call(root.querySelectorAll('.ugc-report'), function (b) {
      b.addEventListener('click', function () {
        if (!confirm('この投稿を通報しますか？')) return;
        fetch(API + '/v1/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ post_id: b.dataset.id }) })
          .then(function () { b.textContent = '通報済み'; b.disabled = true; });
      });
    });
  }
  function submit(e) {
    e.preventDefault();
    var f = e.target, msg = f.querySelector('.ugc-msg'), btn = f.querySelector('button[type=submit]');
    var payload = { site: SITE, key: KEY, kind: f.kind.value, rating: f.rating.value, name: f.name.value, body: f.body.value, website: f.website.value };
    btn.disabled = true; msg.textContent = '送信中…';
    fetch(API + '/v1/posts', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'minna' }, body: JSON.stringify(payload) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok) { msg.textContent = '投稿しました。ありがとうございます。'; load(); }
        else { msg.textContent = res.j.error || '投稿できませんでした'; btn.disabled = false; }
      })
      .catch(function () { msg.textContent = '通信に失敗しました'; btn.disabled = false; });
  }
  function load() {
    fetch(API + '/v1/posts?site=' + encodeURIComponent(SITE) + '&key=' + encodeURIComponent(KEY))
      .then(function (r) { return r.json(); }).then(render).catch(function () { root.innerHTML = ''; });
  }
  load();
})();
