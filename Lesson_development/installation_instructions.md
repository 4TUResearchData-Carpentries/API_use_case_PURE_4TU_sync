## Create a project folder 

In your terminal :

```bash
mkdir wur-pure-reconcile
cd wur-pure-reconcile
```

## Create a virtual environment

- Unix, MacOS

```bash

python3 -m venv .venv
source .venv/bin/activate

```
- Windows (Git Bash)

```bash

python -m venv .venv
source .venv/Scripts/activate

```
## Install the required library

- Create a file called `requirements.txt` with : `requests>=2.31`

```bash

pip install -r requirements.txt

```

## Suggested project structure

wur-pure-reconcile/
├── .venv/
├── wur_pure_reconcile.py
├── requirements.txt
└── 4TU datasets with related publication 20260304.csv