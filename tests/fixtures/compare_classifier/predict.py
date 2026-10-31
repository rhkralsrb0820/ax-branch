"""FIXED TEST PREDICTOR for AX Branch's before/after-training comparison (developer fixture, NOT AI-produced, NOT a
trained model). Keyword rules in ./outputs/<arm>.json stand in for a baseline and a trained model; `mode` simulates
failures. Implements the predict.py contract in axbranch/model_compare.py."""
import argparse
import json
import pathlib
import sys

p = argparse.ArgumentParser()
p.add_argument('--describe', action='store_true')
p.add_argument('--model', choices=('baseline', 'trained'))
p.add_argument('--input')
p.add_argument('--output')
a = p.parse_args()
out = pathlib.Path('outputs')
if a.describe:
    flag = json.loads((out / 'fixture_flag.json').read_text()) if (out / 'fixture_flag.json').is_file() else True
    print(json.dumps({'fixture': flag,
                      'baseline': {'name': 'keyword rules v0 (fixture)', 'files': ['outputs/baseline.json']},
                      'trained': {'name': 'keyword rules v1 (fixture)', 'base_model': 'fixed test rules',
                                  'files': ['outputs/trained.json']}}))
    sys.exit(0)
cfg = json.loads((out / f'{a.model}.json').read_text(encoding='utf-8'))
if cfg.get('mode') == 'crash':
    sys.exit(3)
rows = [json.loads(l) for l in pathlib.Path(a.input).read_text(encoding='utf-8').splitlines() if l.strip()]
lines = []
for r in rows:
    label = next((lab for word, lab in cfg['rules'].items() if word in r['text'].lower()), cfg['default'])
    lines.append(json.dumps({'id': r['id'], 'label': label}))
mode = cfg.get('mode')
if mode == 'missing':
    lines = lines[:-2]
elif mode == 'duplicate':
    lines.append(lines[0])
elif mode == 'badformat':
    lines[0] = 'not json'
pathlib.Path(a.output).write_text('\n'.join(lines) + '\n', encoding='utf-8')
