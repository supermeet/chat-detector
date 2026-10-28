"""Bundle the pipeline into a self-contained Colab notebook (stdlib only).

    python build_notebook.py   ->  SafeSphere_Behavior_Training.ipynb
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ["text_pools.py", "simulate.py", "features.py", "text_model.py", "train.py", "predict.py",
           "external.py", "evaluate.py", "prepare_provided.py", "inspect_provided.py", "diagnose.py"]
cells = []


def md(src):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(True)})


def code(src):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                  "source": src.strip("\n").splitlines(True)})


md("""
# SafeSphere: Behavioural Model Training
Hacksploit 2026 · PS5. This notebook trains the model that tells **stalking / harassment** apart
from **flirting / banter** using behaviour and consent signals.

**Run order:** 1 Setup → 2 Pipeline code → 3 Synthetic data → 4 *Your dataset (optional)* → 5 Train → 6 Evaluate → 7 Try it → 8 Save.
No GPU needed (Runtime → Change runtime type → CPU is fine).
""")
md("## 1. Setup")
code("""
!pip -q install lightgbm pyarrow
import os
os.makedirs('/content/safesphere', exist_ok=True)
%cd /content/safesphere
# Optional: keep everything in Google Drive so it survives a runtime reset
USE_DRIVE = False
if USE_DRIVE:
    from google.colab import drive
    drive.mount('/content/drive')
    os.makedirs('/content/drive/MyDrive/safesphere', exist_ok=True)
""")
md("## 2. Pipeline code\nEach cell writes one module. Edit here or in `ml/behavior/` locally and rebuild the notebook.")
for m in MODULES:
    with open(os.path.join(HERE, m), encoding="utf-8") as fh:
        code(f"%%writefile {m}\n" + fh.read())
md("""
## 3. Load the dataset
**Main data:** the team dataset `safesphere_behavior_dataset.zip` (4,800 train / 1,200 test conversations).
Drag it into the Files pane (left sidebar → 📁 → upload) or run the upload cell below.

We also generate data with our **own simulator** (a different generator with different templates) and train on
**both**. Trained on one generator alone, the model scored F1 0.997 on that generator's test set but only 0.65
on the other's, because it memorised one generator's quirks. Mixing generators fixes that.
""")
code("""
import os
if not os.path.exists('/content/safesphere_behavior_dataset.zip'):
    from google.colab import files
    up = files.upload()   # pick safesphere_behavior_dataset.zip
    for n in up: os.replace(n, f'/content/{n}')
!mkdir -p data/provided && unzip -oq /content/safesphere_behavior_dataset.zip -d data/provided
!python prepare_provided.py --src data/provided/synthetic --out data/prepared
!python simulate.py --n-train 300 --n-test 150 --out data/synthetic
""")
code("!python inspect_provided.py data/prepared/train.parquet | head -n 60")
md("""
## 4. More data (optional)
For any *additional* dataset: upload it, run **inspect** to see the columns, then use one of the converters:
- **Labelled messages** (HASOC / TRAC / Jigsaw: text + label) → improves the text model.
- **Conversations** (chat logs with sender + timestamp) → extra behaviour training / validation.
- **Hand-written test set** (`data/handwritten/*.json`) → honest headline numbers.
""")
code("""
from google.colab import files
os.makedirs('data/raw', exist_ok=True)
uploaded = files.upload()          # pick your dataset file(s)
for name in uploaded:
    os.replace(name, f'data/raw/{name}')
    print('saved', f'data/raw/{name}')
""")
code("""
import glob
for p in glob.glob('data/raw/*'):
    !python external.py inspect "{p}"
""")
code("""
# Fill in the column names after inspecting, then uncomment ONE of these:

# Labelled messages -> data/external/messages.parquet (used by train.py --extra-msgs)
# !python external.py messages data/raw/FILE.csv --text TEXT_COL --label LABEL_COL --map '{"HOF":"insult","NOT":"other"}'

# Conversations -> data/external/conversations.parquet (used by train.py --extra and evaluate.py)
# !python external.py conversations data/raw/FILE.csv --conv CHAT_ID_COL --sender SENDER_COL --user-name "USER" --time TIME_COL --text TEXT_COL --label LABEL_COL

# Hand-written test conversations (folder of JSON files) -> data/external/handwritten.parquet
# !python external.py handwritten data/handwritten
""")
md("## 5. Train\nKeyword baseline, logistic regression, LightGBM multiclass + binary harmful head (monotonic constraints, isotonic calibration). About 2–6 minutes on CPU.")
code("""
extra_files = [p for p in ['data/synthetic/train.parquet', 'data/external/conversations.parquet'] if os.path.exists(p)]
if not os.path.exists('data/prepared/train.parquet'):
    extra_files = extra_files[1:]   # synthetic is already the main training set
extra = ('--extra ' + ' '.join(extra_files)) if extra_files else ''
extra_msgs = '--extra-msgs data/external/messages.parquet' if os.path.exists('data/external/messages.parquet') else ''
train_path = 'data/prepared/train.parquet' if os.path.exists('data/prepared/train.parquet') else 'data/synthetic/train.parquet'
!python train.py --train {train_path} {extra} {extra_msgs} --noise 0.15 --trials 8 --out models
""")
md("## 6. Evaluate\nThe numbers to report are the **hand-written** set (if available) and the **hard-negative false-alarm rate**, not synthetic accuracy alone.")
code("""
test_path = 'data/prepared/test.parquet' if os.path.exists('data/prepared/test.parquet') else 'data/synthetic/test.parquet'
!python evaluate.py --models models --test {test_path} --cross data/synthetic/test.parquet --out reports
""")
code("!python diagnose.py --test data/synthetic/test.parquet   # why are safe people flagged: model vs hard rule")
code("""
from IPython.display import Image, display
import json
for png in ['comparison', 'confusion_matrix', 'pr_curve']:
    display(Image(f'reports/{png}.png', width=520))
m = json.load(open('reports/metrics.json'))
print(json.dumps({k: m[k] for k in m if k not in ('synthetic', 'synthetic_text_model')}, indent=1)[:3000])
""")
md("## 7. Try it: score one conversation")
code("""
import pandas as pd
from predict import Scorer
scorer = Scorer('models')
test = pd.read_parquet(test_path)
for scn in ['stalking', 'safe_mutual', 'harassment_after_no', 'banter']:
    pid = test[test.person_label == scn].person_id.iloc[0]
    r = scorer.score_person(test[test.person_id == pid])
    print(f"\\n[{scn}] risk={r['risk']} level={r['level']} label={r['label']}")
    for s in r['reasons']: print('  ↑', s)
    for s in r['reasons_down']: print('  ↓', s)
""")
md("## 8. Save the trained model\nDownload `safesphere_behavior.zip` and unzip into the backend's `models/` folder.")
code("""
from google.colab import files
!zip -qr safesphere_behavior.zip models reports
if USE_DRIVE:
    !cp -r models reports safesphere_behavior.zip /content/drive/MyDrive/safesphere/
files.download('safesphere_behavior.zip')
""")

nb = {"cells": cells, "metadata": {"colab": {"provenance": [], "name": "SafeSphere_Behavior_Training.ipynb"},
                                   "kernelspec": {"name": "python3", "display_name": "Python 3"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
out = os.path.join(HERE, "SafeSphere_Behavior_Training.ipynb")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(nb, fh, indent=1, ensure_ascii=False)
print("wrote", out)
