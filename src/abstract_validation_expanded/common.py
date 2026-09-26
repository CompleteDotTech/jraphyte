from src.abstract_validation.common import DATA, REPO, digest, read, render, write

OLD = DATA / 'validation_v2'
INDEX = DATA / 'validation_200_10k'
OUT = DATA / 'validation_expanded200'
SEED = 2026092503


def rows():
    return read(OUT / 'manifest.json')['pdfs']


def folder(sid):
    return (OLD if int(sid[1:]) <= 100 else OUT) / 'pages' / sid


def cache(method, sid, suffix='.json'):
    original = OLD / method / (sid + suffix)
    if int(sid[1:]) <= 100 and original.exists():
        return original
    return OUT / method / (sid + suffix)


def code_hashes():
    paths = ['trace_gc/pdf_structure.py', 'trace_gc/pdf_evidence.py',
             'src/abstract_validation_v2/adapters.py',
             'src/abstract_validation_v2/extraction.py',
             'src/abstract_validation_v2/retrieval.py']
    return {p: digest(REPO / p) for p in paths}


def verify_protocol():
    saved = read(OUT / 'protocol.json')
    assert saved['method_hashes'] == code_hashes(), 'Frozen methods changed'
    assert saved['manifest_sha256'] == digest(OUT / 'manifest.json')
    return saved
