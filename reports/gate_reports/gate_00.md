# Stage 0 Gate Report: Environment Bootstrap

Python version: `3.11.6 (tags/v3.11.6:8b6ee5b, Oct  2 2023, 14:57:12) [MSC v.1935 64 bit (AMD64)]`

Interpreter: `<repo-root>\.venv\Scripts\python.exe`

Raw xlsx size (MB): 45.62

Sheet names found: ['Year 2009-2010', 'Year 2010-2011']

## Checks

```
[PASS] Python >= 3.10 sys.version_info(major=3, minor=11, micro=6, releaselevel='final', serial=0)
[PASS] Interpreter is the project .venv <repo-root>\.venv\Scripts\python.exe
[PASS] import pandas 
[PASS] import numpy 
[PASS] import scipy 
[PASS] import sklearn 
[PASS] import matplotlib 
[PASS] import seaborn 
[PASS] import pyarrow 
[PASS] import openpyxl 
[PASS] import yaml 
[PASS] dir exists: data/raw 
[PASS] dir exists: data/interim 
[PASS] dir exists: data/processed 
[PASS] dir exists: data/dashboard 
[PASS] dir exists: db 
[PASS] dir exists: sql 
[PASS] dir exists: src 
[PASS] dir exists: checks 
[PASS] dir exists: notebooks 
[PASS] dir exists: dashboard 
[PASS] dir exists: app 
[PASS] dir exists: app/.streamlit 
[PASS] dir exists: reports/figures 
[PASS] dir exists: reports/gate_reports 
[PASS] dir exists: reports/metrics 
[PASS] dir exists: docs 
[PASS] dir exists: docs/screenshots 
[PASS] dir exists: plan 
[PASS] file non-empty: config.yaml 
[PASS] file non-empty: CLAUDE.md 
[PASS] file non-empty: .gitignore 
[PASS] file non-empty: requirements.txt 
[PASS] cfg.project.seed == 42 42
[PASS] raw xlsx exists, size in [35MB,60MB] size=45622278
[PASS] both configured sheets present ['Year 2009-2010', 'Year 2010-2011']
[PASS] git rev-parse --is-inside-work-tree true
```

## pip freeze

```
altair==6.2.2
anyio==4.15.1
argon2-cffi==25.1.0
argon2-cffi-bindings==26.1.0
arrow==1.4.0
asttokens==3.0.2
async-lru==2.3.0
attrs==26.1.0
babel==2.18.0
beautifulsoup4==4.15.0
bleach==6.4.0
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.1
click==8.5.0
cloudpickle==3.1.2
colorama==0.4.6
comm==0.2.3
contourpy==1.3.3
cycler==0.12.1
debugpy==1.8.21
defusedxml==0.7.1
et_xmlfile==2.0.0
executing==2.2.1
fastjsonschema==2.22.2
fonttools==4.65.0
fqdn==1.5.1
greenlet==3.5.5
h11==0.16.0
httpcore==1.0.9
httptools==0.8.0
httpx==0.28.1
idna==3.19
ipykernel==7.3.0
ipython==9.17.1
ipython_pygments_lexers==1.1.1
isoduration==20.11.0
itsdangerous==2.2.0
jedi==0.20.0
Jinja2==3.1.6
joblib==1.6.0
json5==0.15.0
jsonpointer==3.1.1
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
jupyter-events==0.12.1
jupyter-lsp==2.3.1
jupyter_builder==1.2.3
jupyter_client==8.10.0
jupyter_core==5.9.1
jupyter_server==2.21.0
jupyter_server_terminals==0.5.4
jupyterlab==4.6.3
jupyterlab_pygments==0.3.0
jupyterlab_server==2.28.0
kiwisolver==1.5.1
lark==1.3.1
MarkupSafe==3.0.3
matplotlib==3.11.2
matplotlib-inline==0.2.2
mistune==3.3.4
narwhals==2.26.0
nbclient==0.11.0
nbconvert==7.17.1
nbformat==5.11.1
nest-asyncio2==1.7.2
notebook_shim==0.2.4
numpy==2.4.6
openpyxl==3.1.5
overrides==7.7.0
packaging==26.3
pandas==2.3.3
pandocfilters==1.5.1
parso==0.8.7
pillow==12.3.0
platformdirs==4.11.8
playwright==1.62.0
plotly==7.0.0
prometheus_client==0.26.0
prompt_toolkit==3.0.53
protobuf==7.36.1
psutil==7.2.2
pure_eval==0.2.4
pyarrow==25.0.1
pycparser==3.0
pydeck==0.9.3
pyee==13.0.1
Pygments==2.21.0
pymupdf==1.28.2
pyparsing==3.3.2
pypdf==6.18.1
python-dateutil==2.9.0.post0
python-json-logger==4.2.0
python-multipart==0.0.32
pytz==2026.3.post1
pywinpty==3.0.5
PyYAML==6.0.3
pyzmq==27.2.0
referencing==0.37.0
reportlab==5.0.1
requests==2.34.2
rfc3339-validator==0.1.4
rfc3986-validator==0.1.1
rfc3987-syntax==1.1.0
rpds-py==2026.6.3
scikit-learn==1.9.1
scipy==1.17.1
seaborn==0.13.2
Send2Trash==2.1.0
six==1.17.0
soupsieve==2.9.2
stack-data==0.6.3
starlette==1.6.0
streamlit==1.63.0
terminado==0.18.1
threadpoolctl==3.6.0
tinycss2==1.5.1
toml==0.10.2
tornado==6.5.8
tqdm==4.70.1
traitlets==5.16.1
typing_extensions==4.16.0
tzdata==2026.3
uri-template==1.3.0
urllib3==2.7.0
uvicorn==0.52.4
watchdog==6.0.0
wcwidth==0.8.3
webcolors==25.10.0
webencodings==0.6.1
websocket-client==1.9.2
websockets==16.1.1

```

## GATE: PASS
