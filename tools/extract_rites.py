#!/usr/bin/env python3
"""かんたん命日帳の RiteKindEnum.swift から法要の表を機械的に取り出す。

★書き起こさずに抽出するのは、アプリとページで日付の数え方をズラさないため。
  RiteKindEnum.offset がアプリの正なので、そこを直せばこのJSONも作り直せば追随する。

使い方: python3 tools/extract_rites.py > tools/data/rites.json
"""
import json
import os
import re
import sys

SRC = os.path.expanduser(
    '~/projects/Xcode/MeinichiCho/MeinichiCho/Domain/Rite/ValueObjects/RiteKindEnum.swift')

# 数え方の説明。offset の単位ごとに文章を作る（アプリのコメントの要点をそのまま人向けに）
CATEGORY = {
    'chuin': {'label': '中陰（七日ごと）'},
    'hyakkanichi': {'label': '百箇日'},
    'nenki': {'label': '年忌（仏式）'},
    'reisai': {'label': '霊祭（神式）'},
}

NOTES = {
    'shonanoka': '葬儀の日に繰り上げて行うことが増えています（繰り上げ初七日）。',
    'shijukunichi': '忌明け（きあけ）。香典返しはこのあとに送るのが一般的です。納骨をあわせて行うことも多い日です。',
    'hyakkanichi': '「卒哭忌（そっこくき）」とも呼ばれ、泣くのを終える節目とされます。',
    'isshuki': '亡くなってちょうど1年。ここまでが喪中です。',
    'sankaiki': '一周忌の翌年です。満2年なので、一周忌の1年後にあたります。',
    'sanjusankaiki': '弔い上げ（とむらいあげ）としてここで年忌を終える家が多い区切りです。',
    'gojukkaiki': '弔い上げをさらに先に置く場合の区切りです。',
    'ichinensai': '神式では「年祭」と呼びます。',
    'sannensai': '神式の三年祭は満3年です。仏式の三回忌（満2年）とは1年ずれます。',
}


def main():
    src = open(SRC, encoding='utf-8').read()

    def block(name):
        m = re.search(rf'var {name}:[^{{]*{{\s*switch self {{(.*?)\n        }}\n    }}', src, re.S)
        return m.group(1) if m else ''

    names, aliases, cats, offsets = {}, {}, {}, {}

    for case, val in re.findall(r'case \.(\w+): return "([^"]*)"', block('displayName')):
        names[case] = val
    for case, val in re.findall(r'case \.(\w+): return "([^"]*)"', block('alias')):
        aliases[case] = val
    # category はまとめて列挙されている
    for cases, cat in re.findall(r'case ((?:\.\w+,?\s*)+):\s*\n?\s*return \.(\w+)', block('category')):
        for c in re.findall(r'\.(\w+)', cases):
            cats[c] = cat
    for case, unit, n in re.findall(r'case \.(\w+): return \.(days|years)\((\d+)\)', block('offset')):
        offsets[case] = (unit, int(n))

    rites = []
    for case in names:
        if case not in offsets:
            continue
        unit, n = offsets[case]
        cat = cats.get(case, 'nenki')
        if unit == 'days':
            badge = f'{n}日目'
            summary = f'亡くなった日を1日目として数えて{n}日目（命日の{n - 1}日後）です。'
        else:
            badge = f'満{n}年'
            summary = f'亡くなってから満{n}年の日です。命日と同じ月日にあたります。'
        rites.append({
            'id': case,
            'name': names[case],
            'alias': aliases.get(case, ''),
            'category': cat,
            'badge': badge,
            'summary': summary,
            'note': NOTES.get(case, ''),
            'sortKey': n if unit == 'days' else 1000 + n,
        })

    rites.sort(key=lambda r: (list(CATEGORY).index(r['category']), r['sortKey']))
    for r in rites:
        if r['alias']:
            r['name'] = f"{r['name']}（{r['alias']}）"
        del r['alias'], r['sortKey']

    out = {
        '_source': f'{SRC} の displayName / alias / category / offset から機械抽出（tools/extract_rites.py）。'
                   'アプリの数え方を正とするため、書き起こさずに抽出している。',
        'rites': rites,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == '__main__':
    main()
