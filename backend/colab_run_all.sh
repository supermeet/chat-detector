#!/usr/bin/env bash
# One-shot Colab run: retrain the behaviour model, test the backend, then serve backend + UI on port 8000.
#   Upload safesphere_bundle.zip (repo snapshot) to /content, then:
#   !cd /content && unzip -oq safesphere_bundle.zip -d /tmp/b && bash /tmp/b/backend/colab_run_all.sh
#   Then in Python:  from google.colab.output import serve_kernel_port_as_window; serve_kernel_port_as_window(8000)
set -euo pipefail
cd /content
rm -rf ss && mkdir ss && cd ss && unzip -oq /content/safesphere_bundle.zip
pip -q install lightgbm pyarrow fastapi python-multipart reportlab httpx pytest uvicorn
python -c "import sklearn, lightgbm, pandas, fastapi; print('versions: sklearn', sklearn.__version__, '| lightgbm', lightgbm.__version__, '| pandas', pandas.__version__, '| fastapi', fastapi.__version__)"

cd /content/ss/ml/behavior
mkdir -p data/provided && unzip -oq /content/ss/data/safesphere_behavior_dataset.zip -d data/provided
python prepare_provided.py --src data/provided/synthetic --out data/prepared
python simulate.py --n-train 300 --n-test 150 --out data/synthetic > /dev/null
python train.py --train data/prepared/train.parquet --extra data/synthetic/train.parquet --trials 8 --out models | grep -v trial
python evaluate.py --test data/prepared/test.parquet --cross data/synthetic/test.parquet --skip-ttd --out reports 2>&1 \
  | grep -v -i warning | grep -v "kw = " | grep -E "==|keyword|lightgbm|macro|saved"

mkdir -p /content/ss/backend/models
cp models/behavior_model.pkl models/text_models.pkl reports/metrics.json /content/ss/backend/models/
cd /content/ss && zip -qr /content/safesphere_trained_models.zip backend/models ml/behavior/reports
echo "models zipped: /content/safesphere_trained_models.zip"

cd /content/ss/backend
python -m pytest -q -p no:cacheprovider 2>&1 | tail -n 30
pkill -f "uvicorn app.main:app" || true
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /content/uvicorn.log 2>&1 &
sleep 4 && curl -s localhost:8000/health | head -c 300 && echo
echo "DONE: backend + UI on port 8000"
