"""Read-only production extraction, using the production Python/PyMuPDF runtime."""
import platform
import sys
import time

from .common import DATA, OUT, digest, read, write


def main():
    sys.path.insert(0, str(DATA))
    import run_jev_corpus as current
    import fitz
    write(OUT / 'baselines/production_environment.json', {
        'python': platform.python_version(), 'pymupdf': fitz.VersionBind,
        'runner_sha256': digest(current.__file__), 'database_access': 'none'})
    for row in read(OUT / 'holdout_manifest.json')['pdfs']:
        dest = OUT / 'baselines/current' / (row['sample_id'] + '.json')
        if dest.exists():
            continue
        started = time.monotonic()
        try:
            # Use the original file, exactly as the live extractor does.
            source_hash, text, method = current.abstract_from_pdf(row['source_path'])
            result = {'text': text, 'method': method, 'source_sha256': source_hash}
        except Exception as exc:
            result = {'text': '', 'error': type(exc).__name__ + ': ' + str(exc)}
        write(dest, {**result, 'seconds': time.monotonic()-started})
    print('Production baseline: 200 completed; no database writes or API calls')


if __name__ == '__main__':
    main()
