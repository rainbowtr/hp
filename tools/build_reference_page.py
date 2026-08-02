#!/usr/bin/env python3
"""検索クエリに答える実用ページ（LP兼SEO）を、アプリが持っているデータから生成する。

なぜ要るか（2026-08-02 の実測）:
  かんたん洗濯表示は App Store で「洗濯表示」4位/19件 と上位にいるのに 28日で4DL しかない。
  Appleのサジェストも4件しか埋まらない＝**App Store の検索窓にその需要が来ていない**。
  一方「洗濯表示 一覧／意味」は Google 側に大きな需要がある。
  だから戦う場所を店の外に置く: クエリに完全に答えるページを出し、
  ページにできないこと（タグを撮って判定する）だけをアプリの仕事として渡す。

★この型は他レーンに使い回す前提。データ(JSON)と設定を差し替えれば同じ形が出る:
  香典の金額相場 / 続柄の呼び方 / 四十九日の数え方 / ゴミの分別 / 食品表示の文字サイズ など。

使い方:
  python3 tools/build_reference_page.py --config tools/pages/sentaku-hyoji.json
"""
import argparse
import html
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)


def esc(s):
    return html.escape(str(s or ''), quote=True)


def load_symbols(cfg):
    with open(os.path.expanduser(cfg['dataPath']), encoding='utf-8') as f:
        data = json.load(f)
    for key in cfg.get('dataKeyPath', []):
        data = data[key]
    return data


def copy_assets(cfg, items, outdir):
    """図版SVGをサイト側へ複製（アプリ側を正とし、ここは常に上書き）"""
    src = os.path.expanduser(cfg['assetDir'])
    dst = os.path.join(outdir, 'symbols')
    os.makedirs(dst, exist_ok=True)
    copied = 0
    for item in items:
        name = f"{item['id']}.svg"
        s = os.path.join(src, name)
        if os.path.exists(s):
            shutil.copyfile(s, os.path.join(dst, name))
            copied += 1
    return copied


def card_html(item, cfg):
    cat = cfg['categories'][item['category']]
    gen_label = '新JIS' if item['generation'] == cfg['currentGeneration'] else '旧JIS'
    gen_class = 'new' if item['generation'] == cfg['currentGeneration'] else 'old'

    lines = []
    for d in item.get('dos') or []:
        lines.append(f'<li class="do">{esc(d)}</li>')
    for d in item.get('donts') or []:
        lines.append(f'<li class="dont">{esc(d)}</li>')
    actions = f'<ul class="actions">{"".join(lines)}</ul>' if lines else ''

    # 検索用の素の文字列（アクセント記号なし・ページ内検索で拾う）
    haystack = ' '.join(filter(None, [
        item.get('name'), item.get('meaning'), item.get('plain'), cat['label'], gen_label,
    ]))

    return f'''<article class="card" id="{esc(item['id'])}" data-cat="{esc(item['category'])}" data-gen="{gen_class}" data-q="{esc(haystack)}">
  <div class="figure"><img src="symbols/{esc(item['id'])}.svg" alt="{esc(item['name'])}の洗濯表示マーク" loading="lazy" width="72" height="72"></div>
  <div class="body">
    <div class="tags"><span class="tag cat-{esc(item['category'])}">{esc(cat['label'])}</span><span class="tag gen-{gen_class}">{gen_label}</span></div>
    <h3>{esc(item['name'])}</h3>
    <p class="meaning">{esc(item['meaning'])}</p>
    <p class="plain">{esc(item.get('plain'))}</p>
    {actions}
    <p class="source">{esc(item.get('sourceNote'))}</p>
  </div>
</article>'''


def mapping_rows(items, cfg):
    by_id = {i['id']: i for i in items}
    rows = []
    for item in items:
        if item['generation'] == cfg['currentGeneration']:
            continue
        news = [by_id[n] for n in (item.get('newEquivalentIds') or []) if n in by_id]
        if not news:
            continue
        new_cells = ''.join(
            f'<a class="minicell" href="#{esc(n["id"])}"><img src="symbols/{esc(n["id"])}.svg" alt="" width="34" height="34"><span>{esc(n["name"])}</span></a>'
            for n in news
        )
        rows.append(
            f'<tr><td class="old"><a class="minicell" href="#{esc(item["id"])}">'
            f'<img src="symbols/{esc(item["id"])}.svg" alt="" width="34" height="34"><span>{esc(item["name"])}</span></a></td>'
            f'<td class="arrow">→</td><td>{new_cells}</td></tr>'
        )
    return '\n'.join(rows)


def app_url(cfg):
    """App Store リンクにキャンペーンを付ける。

    ★これで「このページ経由で何本落ちたか」が App Store Connect の
      Analytics（流入元 / Campaign）に出る。**JSもCookieも要らない**ので、
      GA4を入れるより先にこちらを当てる（同意バナーもプライバシーポリシー改訂も不要）。
      rank 側では `node cli.js sources` の campaign に slug が並ぶ。
    """
    url = cfg['app']['url']
    ct = cfg.get('campaign') or f"lp-{cfg['slug']}"
    sep = '&' if '?' in url else '?'
    return f'{url}{sep}ct={urllib_quote(ct)}&mt=8'


def urllib_quote(s):
    import urllib.parse
    return urllib.parse.quote(str(s), safe='')


def faq_html(cfg):
    blocks, ld = [], []
    for qa in cfg.get('faq', []):
        blocks.append(f'<details><summary>{esc(qa["q"])}</summary><div>{qa["a"]}</div></details>')
        # JSON-LD には素のテキストを入れる（タグは落とす）
        ld.append({
            '@type': 'Question',
            'name': qa['q'],
            'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'<[^>]+>', '', qa['a'])},
        })
    return '\n'.join(blocks), ld


def build(cfg_path):
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)

    items = load_symbols(cfg)
    outdir = os.path.join(SITE, cfg['slug'])
    os.makedirs(outdir, exist_ok=True)
    copied = copy_assets(cfg, items, outdir)

    order = list(cfg['categories'].keys())
    items.sort(key=lambda i: (order.index(i['category']), i['generation'] != cfg['currentGeneration']))

    cards = '\n'.join(card_html(i, cfg) for i in items)
    chips = '\n'.join(
        f'<button class="chip" data-filter="cat" data-value="{esc(k)}">{esc(v["label"])}</button>'
        for k, v in cfg['categories'].items()
    )
    faq_blocks, faq_ld = faq_html(cfg)

    n_new = sum(1 for i in items if i['generation'] == cfg['currentGeneration'])
    n_old = len(items) - n_new

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
           .replace('{{COUNT_NEW}}', str(n_new))
           .replace('{{COUNT_OLD}}', str(n_old))
           .replace('{{CHIPS}}', chips)
           .replace('{{CARDS}}', cards)
           .replace('{{MAPPING_ROWS}}', mapping_rows(items, cfg))
           .replace('{{FAQ}}', faq_blocks)
           .replace('{{APP_NAME}}', esc(cfg['app']['name']))
           .replace('{{APP_PITCH}}', cfg['app']['pitch'])
           .replace('{{APP_URL}}', esc(app_url(cfg)))
           .replace('{{JSONLD}}', json.dumps(jsonld, ensure_ascii=False)))

    path = os.path.join(outdir, 'index.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'✅ {path}  記号{len(items)}件（新{n_new}/旧{n_old}）・SVG{copied}件')
    return path


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    build(ap.parse_args().config)
