"""Run both pinned local vision models on the same 200 first pages."""
import argparse
import ast
import time
from PIL import Image
from .common import OLD, OUT, cache, digest, folder, read, rows, verify_protocol, write


def main():
    p = argparse.ArgumentParser()
    p.add_argument('method', choices=['mineru', 'olmocr'])
    args = p.parse_args()
    verify_protocol()
    import torch
    import pymupdf
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    torch.set_num_threads(4)
    torch.manual_seed(2026092502)
    name = 'opendatalab/MinerU2.5-2509-1.2B' if args.method == 'mineru' else 'allenai/olmOCR-2-7B-1025'
    model_path = read(OLD / 'model_paths.json')[name]
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    started = time.perf_counter()
    kwargs = dict(torch_dtype=torch.bfloat16, device_map='cuda:0', attn_implementation='sdpa', local_files_only=True)
    if args.method == 'olmocr':
        kwargs['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForImageTextToText.from_pretrained(model_path, **kwargs).eval()
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
    if args.method == 'mineru':
        from mineru_vl_utils import MinerUClient
        client = MinerUClient(backend='transformers', model=model, processor=processor, batch_size=1, max_concurrency=1, use_tqdm=False, skip_model_name_checking=True)
    else:
        tree = ast.parse((OLD / 'environment/olmocr_prompts.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_no_anchoring_v4_yaml_prompt')
        prompt = ast.literal_eval(next(n.value for n in fn.body if isinstance(n, ast.Return)))
    write(OUT / args.method / 'configuration.json', {
        **read(OLD / args.method / 'configuration.json'),
        'setup_seconds':time.perf_counter()-started,
        'scope':'200 first pages; prior 20 fresh-page outputs reused; no API calls',
        'runner_sha256':digest(__file__),
    })
    for position, row in enumerate(rows(), 1):
        sid = row['sample_id']
        page = folder(sid) / 'page.pdf'
        source_hash = digest(page)
        dest = cache(args.method, sid)
        if dest.exists():
            assert read(dest)['page_sha256'] == source_hash, sid
            print({'reused':sid, 'method':args.method, 'position':position}, flush=True)
            continue
        with pymupdf.open(page) as pdf:
            pix = pdf[0].get_pixmap(dpi=200)
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
        if args.method == 'olmocr':
            img.thumbnail((1288, 1288))
        started = time.perf_counter()
        try:
            with torch.inference_mode():
                if args.method == 'mineru':
                    blocks = client.two_step_extract(img)
                    result = {'blocks':[dict(b) if isinstance(b, dict) else vars(b) for b in blocks], 'status':'success'}
                else:
                    messages = [{'role':'user', 'content':[{'type':'text','text':prompt}, {'type':'image','image':img}]}]
                    rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                    inputs = processor(text=[rendered], images=[img], return_tensors='pt').to('cuda:0')
                    output = model.generate(**inputs, max_new_tokens=4096, do_sample=False)
                    generated = output[0, inputs['input_ids'].shape[1]:]
                    result = {'raw_text':processor.decode(generated, skip_special_tokens=True), 'output_tokens':len(generated), 'status':'success' if len(generated)<4096 else 'truncated'}
                    del inputs, output, generated
        except Exception as exc:
            result = {'status':'error', 'error':type(exc).__name__+': '+str(exc)[:500]}
            torch.cuda.empty_cache()
        result.update(seconds=time.perf_counter()-started, page_sha256=source_hash, sample_id=sid)
        write(dest, result)
        print({'processed':sid, 'method':args.method, 'position':position, 'seconds':round(result['seconds'],1), 'state':result['status']}, flush=True)


if __name__ == '__main__':
    main()
