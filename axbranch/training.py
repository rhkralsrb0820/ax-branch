"""Model training capability: real weight training (e.g. LoRA) of small public models on this PC's CPU, in a
pinned environment (one per pin set, short path) acquired from the official PyTorch CPU index and PyPI (free). No GPU is
available here; a free cloud GPU needs the Owner to sign in, so that option only ever yields a decision record.
"""
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .native import ToolUnavailable, _run

PINS = ('torch==2.14.1+cpu', 'transformers==5.20.2', 'peft==0.21.2', 'accelerate==1.15.0', 'scikit-learn==1.9.1')
TORCH_INDEX = 'https://download.pytorch.org/whl/cpu'
ENV_TIMEOUT = 1800        # seconds to create the environment (large wheels)
PROBE_SECONDS = 300       # the feasibility run must finish well inside this

# A real LoRA update on a tiny randomly initialised model (no download): base weights stay frozen, the adapter
# changes, and the loss moves. It proves the toolchain trains on this CPU and measures its speed.
PROBE = r'''
import json, time, torch
from transformers import BertConfig, BertForSequenceClassification
from peft import LoraConfig, get_peft_model
torch.manual_seed(0)
model = BertForSequenceClassification(BertConfig(vocab_size=200, hidden_size=64, num_hidden_layers=2,
                                                 num_attention_heads=2, intermediate_size=128, num_labels=4))
model = get_peft_model(model, LoraConfig(r=4, lora_alpha=8, target_modules=['query', 'value'], task_type='SEQ_CLS'))
lora = {n: p.detach().clone() for n, p in model.named_parameters() if 'lora_B' in n}
base = {n: p.detach().clone() for n, p in model.named_parameters() if 'query.base_layer.weight' in n}
x, y = torch.randint(0, 200, (32, 16)), torch.randint(0, 4, (32,))
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-2)
start, losses = time.monotonic(), []
for _ in range(30):
    out = model(input_ids=x, labels=y); out.loss.backward(); opt.step(); opt.zero_grad(); losses.append(out.loss.item())
params = dict(model.named_parameters())
print(json.dumps({'steps': 30, 'seconds': round(time.monotonic() - start, 2), 'loss_first': losses[0],
                  'loss_last': losses[-1], 'torch': torch.__version__,
                  'trainable': sum(p.numel() for p in model.parameters() if p.requires_grad),
                  'total': sum(p.numel() for p in model.parameters()),
                  'adapter_changed': any(not torch.equal(lora[n], params[n]) for n in lora),
                  'base_frozen': all(torch.equal(base[n], params[n]) for n in base)}))
'''


def env_python(project_dir=None):
    """One environment per exact pin set, at a SHORT path: torch's deepest header exceeded Windows' 260-character
    limit under a project folder (real probe 2026-10-22; long paths are an admin setting, not ours to change).
    Keyed by the pins, so every project reuses the same verified stack instead of downloading it again."""
    tag = hashlib.sha256(' '.join(PINS).encode('utf-8')).hexdigest()[:8]
    venv = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'axb' / f'te-{tag}'
    return venv, venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def ensure_env(project_dir, python=None):
    """The project's isolated training environment (created once; the marker is written last)."""
    venv, vpy = env_python(project_dir)
    done = venv / 'AXB_INSTALLED'
    if vpy.is_file() and done.is_file() and done.read_text(encoding='utf-8') == ' '.join(PINS):
        return {'tool': 'training-env', 'pins': list(PINS), 'python': str(vpy), 'acquired': False}
    shutil.rmtree(venv, ignore_errors=True)
    started = time.monotonic()
    try:
        code, out = _run([python or sys.executable, '-m', 'venv', str(venv)], str(project_dir), ENV_TIMEOUT)
        if code != 0:
            raise ToolUnavailable(f'venv creation failed (exit {code}): {out[-400:]}')
        code, out = _run([vpy, '-m', 'pip', 'install', '--isolated', '--disable-pip-version-check', '--no-input',
                          '--no-cache-dir', '--index-url', TORCH_INDEX, '--extra-index-url', 'https://pypi.org/simple',
                          *PINS], str(project_dir), ENV_TIMEOUT)
        if code != 0:
            raise ToolUnavailable(f'pip install of the training stack failed (exit {code}): {out[-600:]}')
        done.write_text(' '.join(PINS), encoding='utf-8')
    except BaseException as e:
        shutil.rmtree(venv, ignore_errors=True)      # never leave a half environment that looks installed
        if isinstance(e, ToolUnavailable):
            raise
        raise ToolUnavailable(f'training environment failed: {type(e).__name__}: {e}') from None
    return {'tool': 'training-env', 'pins': list(PINS), 'python': str(vpy), 'acquired': True,
            'seconds': round(time.monotonic() - started), 'source': f'{TORCH_INDEX} + PyPI (pip)'}


def probe_cpu(project_dir):
    """Option 1 (free, local): acquire the pinned stack and run a real tiny LoRA update within PROBE_SECONDS."""
    try:
        env = ensure_env(project_dir)
    except ToolUnavailable as e:
        return {'ok': False, 'why': str(e)[:600]}
    code, out = _run([env['python'], '-c', PROBE], str(project_dir), PROBE_SECONDS)
    lines = [ln for ln in out.strip().splitlines() if ln.startswith('{')]
    try:
        result = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        result = None
    if code != 0 or not result:
        return {'ok': False, 'why': f'LoRA probe failed (exit {code}): {out[-600:]}', 'environment': env}
    if not (result['adapter_changed'] and result['base_frozen']):
        return {'ok': False, 'why': 'LoRA probe ran but did not train only the adapter', 'evidence': result}
    return {'ok': True, 'evidence': result, 'environment': env}


def probe_cloud_gpu(project_dir):
    """Option 2 (free tier, needs the Owner): no authorized connection exists on this PC, so this is a decision."""
    return {'ok': False, 'why': 'no authorized cloud GPU connection on this PC (no signed-in Colab/Kaggle session or '
                                'connector); free-tier GPU allocation is not guaranteed even after sign-in',
            'minimal_approval': 'Owner signs in to Google Colab (or Kaggle) and approves one notebook connection that '
                                'runs the prepared training job and returns the adapter files and metrics',
            'cost': '0 on the free tiers; paid tiers exist (price UNKNOWN until checked on the vendor page)'}
