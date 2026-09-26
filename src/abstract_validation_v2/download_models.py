"""Pin public model revisions and download weights; no inference API calls."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from huggingface_hub import snapshot_download
from .common import OUT, read, write

MODELS = {
    'opendatalab/MinerU2.5-2509-1.2B':'1aa090b41282e64fadd79c10572221f91ec21924',
    'allenai/olmOCR-2-7B-1025':'e52d6f090b7a9007afffbbd6ce510876222fea93',
    'allenai/specter2_base':'3447645e1def9117997203454fa4495937bfbd83',
    'allenai/specter2':'2081559630a80fc5851d8f798a05ba81e9468089',
    'allenai/specter2_adhoc_query':'3f4448817028388648a74349ece07af4518ec5bd',
    'cross-encoder/ms-marco-MiniLM-L-6-v2':'233902d25c440f23af6f7d6e94d2946bac0bee0a'}


def main():
    dest = OUT / 'model_revisions.json'
    if not dest.exists():
        write(dest, MODELS)
    revisions = read(dest)
    assert revisions==MODELS,'Model revisions differ from the tested pins'
    def download(name):
        path = snapshot_download(name, revision=revisions[name], local_dir=OUT/'models'/name.replace('/','--'),
            allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.bin', '*.py', '*.jinja'],
            ignore_patterns=['tf_model*', 'flax_model*', 'onnx/*', 'openvino/*'], max_workers=2)
        print({'downloaded': name, 'revision': revisions[name]}, flush=True)
        return name, path
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = {}
        for future in as_completed([pool.submit(download,name) for name in MODELS]):
            name,path=future.result(); paths[name]=str(path)
            write(OUT / 'model_paths.json', paths)


if __name__ == '__main__':
    main()
