# Dataset goes here

1. Open https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature (free Kaggle account needed).
2. Click **Download**, unzip, and put `measures_v2.csv` in this folder:

```
data/measures_v2.csv
```

Or with the Kaggle CLI (`pip install kaggle`, API token in `~/.kaggle/kaggle.json`):

```bash
kaggle datasets download -d wkirgsn/electric-motor-temperature -p data --unzip
```

The CSV is not committed to Git (see `.gitignore`) because of its size.
