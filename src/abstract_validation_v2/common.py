from src.abstract_validation.common import DATA, REPO, digest, read, render, write

PREVIOUS = DATA / 'validation_200_10k'
OUT = DATA / 'validation_v2'
SEED = 2026092502


def rows():
    return read(OUT / 'holdout_manifest.json')['pdfs']


def page_folder(row):
    return OUT / 'pages' / row['sample_id']
