#!/usr/bin/env python3
"""検索クエリに答える実用ページ（LP兼SEO）を、アプリが持っているデータから生成する。

なぜ要るか（2026-08-02 の実測）:
  かんたん洗濯表示は App Store で「洗濯表示」4位/19件 と上位にいるのに 28日で4DL しかない。
  Appleのサジェストも4件しか埋まらない＝**App Store の検索窓にその需要が来ていない**。
  一方「洗濯表示 一覧／意味」は Google 側に大きな需要がある。
  だから戦う場所を店の外に置く: クエリに完全に答えるページを出し、
  ページにできないこと（タグを撮って判定する）だけをアプリの仕事として渡す。

★どのレーンに当てるかは3条件で決める（[[seo-landing-page-lane]]）:
  ① Appleサジェストが埋まらない（App Store側に需要が無い）
  ② Googleに情報クエリがある
  ③ その答えのデータをアプリが既に持っている ← これが無いと薄いページになって順位が付かない

使い方:
  python3 tools/build_reference_page.py --config tools/pages/<slug>.json
  python3 tools/build_reference_page.py --all
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)


def esc(s):
    return html.escape(str(s or ''), quote=True)


def load_items(cfg):
    with open(os.path.expanduser(cfg['data']['path']), encoding='utf-8') as f:
        data = json.load(f)
    for key in cfg['data'].get('keyPath', []):
        data = data[key]
    return data


def field(item, cfg, name, default=''):
    """config の fields 対応表を通して値を取る。未設定/欠損は default"""
    key = cfg.get('fields', {}).get(name)
    if not key:
        return default
    value = item.get(key)
    return default if value in (None, '') else value


def item_id(item, cfg, index):
    raw = field(item, cfg, 'id')
    if raw:
        return str(raw)
    # idを持たないデータ（分別辞書など）は連番。アンカーが安定するよう index を使う
    return f'i{index}'


def copy_assets(cfg, items, outdir):
    """図版をサイト側へ複製（アプリ側を正とし、常に上書き）。assets 未設定なら何もしない"""
    assets = cfg.get('assets')
    if not assets:
        return 0
    src = os.path.expanduser(assets['dir'])
    ext = assets.get('ext', 'svg')
    dst = os.path.join(outdir, 'figures')
    os.makedirs(dst, exist_ok=True)
    copied = 0
    for i, item in enumerate(items):
        name = f'{item_id(item, cfg, i)}.{ext}'
        s = os.path.join(src, name)
        if os.path.exists(s):
            shutil.copyfile(s, os.path.join(dst, name))
            copied += 1
    return copied


def has_asset(cfg, item, index, outdir):
    if not cfg.get('assets'):
        return False
    ext = cfg['assets'].get('ext', 'svg')
    return os.path.exists(os.path.join(outdir, 'figures', f'{item_id(item, cfg, index)}.{ext}'))


def generation_of(item, cfg):
    """新旧の区別を持つデータ（洗濯表示）だけで使う。無ければ None"""
    gens = cfg.get('generations')
    if not gens:
        return None
    value = field(item, cfg, 'generation')
    is_current = value == gens['current']
    return {
        'cls': 'new' if is_current else 'old',
        'label': gens['currentLabel'] if is_current else gens['oldLabel'],
    }


def card_html(item, cfg, index, outdir):
    cat_key = field(item, cfg, 'category')
    cat = cfg['categories'].get(cat_key, {'label': cat_key or ''})
    gen = generation_of(item, cfg)
    iid = item_id(item, cfg, index)

    lines = []
    for d in field(item, cfg, 'dos', []) or []:
        lines.append(f'<li class="do">{esc(d)}</li>')
    for d in field(item, cfg, 'donts', []) or []:
        lines.append(f'<li class="dont">{esc(d)}</li>')
    actions = f'<ul class="actions">{"".join(lines)}</ul>' if lines else ''

    # 検索用の素の文字列。config の search で読み仮名なども足せる
    parts = [field(item, cfg, 'title'), field(item, cfg, 'summary'), field(item, cfg, 'detail'), cat['label']]
    if gen:
        parts.append(gen['label'])
    for extra in cfg.get('fields', {}).get('search', []):
        parts.append(item.get(extra) or '')
    if cfg.get('fields', {}).get('badge'):
        parts.append(cfg.get('badgeFormat', '{}').format(field(item, cfg, 'badge', '')))
    haystack = ' '.join(str(p) for p in parts if p)

    if has_asset(cfg, item, index, outdir):
        ext = cfg['assets'].get('ext', 'svg')
        figure = (f'<div class="figure"><img src="figures/{esc(iid)}.{ext}" '
                  f'alt="{esc(field(item, cfg, "title"))}の{esc(cfg.get("figureAlt", "図"))}" '
                  f'loading="lazy" width="88" height="88"></div>')
    else:
        figure = ''

    gen_tag = f'<span class="tag gen-{gen["cls"]}">{gen["label"]}</span>' if gen else ''
    # 数値そのものが答えになるデータ（親等・命日からの日数）はバッジで前に出す
    badge_raw = field(item, cfg, 'badge')
    badge = ''
    if badge_raw != '' or badge_raw == 0:
        fmt = cfg.get('badgeFormat', '{}')
        badge = f'<span class="tag badge">{esc(fmt.format(badge_raw))}</span>'
    summary = field(item, cfg, 'summary')
    detail = field(item, cfg, 'detail')
    source = field(item, cfg, 'source')

    return f'''<article class="card{'' if figure else ' nofig'}" id="{esc(iid)}" data-cat="{esc(cat_key)}"{f' data-gen="{gen["cls"]}"' if gen else ''} data-q="{esc(haystack)}">
  {figure}
  <div class="body">
    <div class="tags"><span class="tag cat">{esc(cat['label'])}</span>{gen_tag}{badge}</div>
    <h3>{esc(field(item, cfg, 'title'))}</h3>
    {f'<p class="meaning">{esc(summary)}</p>' if summary else ''}
    {f'<p class="plain">{esc(detail)}</p>' if detail else ''}
    {actions}
    {f'<p class="source">{esc(source)}</p>' if source else ''}
  </div>
</article>'''


def mapping_section(items, cfg, outdir):
    """新旧の対応表。mapping を持つデータ（洗濯表示）だけ出す"""
    mapping = cfg.get('mapping')
    gens = cfg.get('generations')
    if not (mapping and gens):
        return ''
    by_id = {item_id(it, cfg, i): (it, i) for i, it in enumerate(items)}
    rows = []
    for i, item in enumerate(items):
        if field(item, cfg, 'generation') == gens['current']:
            continue
        targets = [by_id[n] for n in (item.get(mapping['field']) or []) if n in by_id]
        if not targets:
            continue
        cells = ''.join(
            f'<a class="minicell" href="#{esc(item_id(t, cfg, ti))}">'
            + (f'<img src="figures/{esc(item_id(t, cfg, ti))}.{cfg["assets"].get("ext", "svg")}" alt="" width="36" height="36">'
               if has_asset(cfg, t, ti, outdir) else '')
            + f'<span>{esc(field(t, cfg, "title"))}</span></a>'
            for t, ti in targets
        )
        img = (f'<img src="figures/{esc(item_id(item, cfg, i))}.{cfg["assets"].get("ext", "svg")}" alt="" width="36" height="36">'
               if has_asset(cfg, item, i, outdir) else '')
        rows.append(
            f'<tr><td><a class="minicell" href="#{esc(item_id(item, cfg, i))}">{img}'
            f'<span>{esc(field(item, cfg, "title"))}</span></a></td>'
            f'<td class="arrow">→</td><td>{cells}</td></tr>'
        )
    if not rows:
        return ''
    return (f'<h2>{esc(mapping["title"])}</h2>\n<div class="tablewrap"><table><tbody>\n'
            + '\n'.join(rows) + '\n</tbody></table></div>')


def faq_html(cfg):
    blocks, ld = [], []
    for qa in cfg.get('faq', []):
        blocks.append(f'<details><summary>{esc(qa["q"])}</summary><div>{qa["a"]}</div></details>')
        ld.append({
            '@type': 'Question',
            'name': qa['q'],
            'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'<[^>]+>', '', qa['a'])},
        })
    return '\n'.join(blocks), ld


def app_url(cfg):
    """App Store リンクにキャンペーンを付ける。

    ★これで「このページ経由で何本落ちたか」が App Store Connect の
      Analytics（流入元 / Campaign）に出る。**JSもCookieも要らない**ので、
      GA4を入れるより先にこちらを当てる。rank 側では `node cli.js sources` の campaign に並ぶ。
    """
    url = cfg['app']['url']
    ct = cfg.get('campaign') or f"lp-{cfg['slug']}"
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}ct={urllib.parse.quote(ct, safe='')}&mt=8"


def app_is_live(cfg):
    """App Store のページが実在するか。

    ★審査中のアプリのリンクを載せると CTA が404になる（2026-08-02 に命日帳で踏んだ）。
      config の "live": false で明示的に伏せられるし、--check-links を付ければ
      ビルド時に実際に叩いて確かめる。読み手に死んだリンクを踏ませない。
    """
    if cfg['app'].get('live') is False:
        return False, '設定で live:false'
    if not CHECK_LINKS:
        return True, ''
    import urllib.request
    try:
        req = urllib.request.Request(cfg['app']['url'], method='HEAD',
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 400, f'HTTP {r.status}'
    except Exception as e:
        return False, str(e)[:60]


CHECK_LINKS = False


def build(cfg_path):
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)

    items = load_items(cfg)
    outdir = os.path.join(SITE, cfg['slug'])
    os.makedirs(outdir, exist_ok=True)
    copied = copy_assets(cfg, items, outdir)

    order = list(cfg['categories'].keys())
    gens = cfg.get('generations')

    def sort_key(pair):
        i, item = pair
        c = field(item, cfg, 'category')
        ci = order.index(c) if c in order else len(order)
        gi = 0
        if gens:
            gi = 0 if field(item, cfg, 'generation') == gens['current'] else 1
        return (ci, gi, i)

    items = [it for _, it in sorted(enumerate(items), key=sort_key)]

    cards = '\n'.join(card_html(it, cfg, i, outdir) for i, it in enumerate(items))
    chips = '\n'.join(
        f'<button class="chip" data-filter="cat" data-value="{esc(k)}">{esc(v["label"])}</button>'
        for k, v in cfg['categories'].items()
    )
    if gens:
        chips += (f'\n<button class="chip" data-filter="gen" data-value="new">{esc(gens["currentLabel"])}だけ</button>'
                  f'\n<button class="chip" data-filter="gen" data-value="old">{esc(gens["oldLabel"])}だけ</button>')
    faq_blocks, faq_ld = faq_html(cfg)

    live, why = app_is_live(cfg)
    if live:
        appbox = (f'<div class="appbox"><h2>{esc(cfg["app"].get("heading", "アプリでもっと早く"))}</h2>'
                  f'<p>{cfg["app"]["pitch"]}</p>'
                  f'<a class="appbadge" href="{esc(app_url(cfg))}">'
                  f'<img src="/images/app-store-badge-ja.svg" '
                  f'alt="{esc(cfg["app"]["name"])}を App Store でダウンロード" width="147" height="54"></a></div>')
    else:
        appbox = ''
        print(f'   ⚠️ {cfg["slug"]}: アプリのリンクを伏せました（{why}）。公開後に live を戻して作り直すこと')

    jsonld = {
        '@context': 'https://schema.org',
        '@graph': [
            {'@type': 'WebPage', 'name': cfg['title'], 'description': cfg['description'],
             'url': cfg['canonical'], 'inLanguage': 'ja'},
            {'@type': 'FAQPage', 'mainEntity': faq_ld},
        ],
    }

    with open(os.path.join(HERE, 'reference_page.html'), encoding='utf-8') as f:
        tmpl = f.read()

    out = (tmpl
           .replace('{{TITLE}}', esc(cfg['title']))
           .replace('{{DESCRIPTION}}', esc(cfg['description']))
           .replace('{{CANONICAL}}', esc(cfg['canonical']))
           .replace('{{H1}}', esc(cfg['h1']))
           .replace('{{LEAD}}', cfg['lead'])
           .replace('{{COUNTS}}', cfg.get('counts', f'全{len(items)}件を載せています。'))
           .replace('{{LEGEND}}', esc(cfg.get('legend', '押すと絞り込めます。')))
           .replace('{{SEARCH_PLACEHOLDER}}', esc(cfg.get('searchPlaceholder', '名前で探す')))
           .replace('{{CHIPS}}', chips)
           .replace('{{GRID_CLASS}}', 'grid' if copied else 'grid compact')
           .replace('{{CARDS}}', cards)
           .replace('{{MAPPING}}', mapping_section(items, cfg, outdir))
           .replace('{{APPBOX}}', appbox)
           .replace('{{FAQ}}', faq_blocks)
           .replace('{{FOOTNOTE}}', cfg['footnote'])
           .replace('{{JSONLD}}', json.dumps(jsonld, ensure_ascii=False)))

    path = os.path.join(outdir, 'index.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'✅ /{cfg["slug"]}/  {len(items)}件' + (f'・図版{copied}件' if copied else '・図版なし'))
    return path


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--config')
    ap.add_argument('--all', action='store_true', help='tools/pages/*.json を全部作り直す')
    ap.add_argument('--check-links', action='store_true', help='App Storeのリンクが生きているか実際に叩いて確かめる')
    a = ap.parse_args()
    globals()['CHECK_LINKS'] = a.check_links
    if a.all:
        for p in sorted(glob.glob(os.path.join(HERE, 'pages', '*.json'))):
            build(p)
    elif a.config:
        build(a.config)
    else:
        ap.error('--config か --all が要ります')
