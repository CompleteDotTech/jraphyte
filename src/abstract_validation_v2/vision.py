"""Paired local fallback pilot, with input hashes and raw model outputs."""
import argparse
import ast
import random
import time
from PIL import Image
from .common import OUT, PREVIOUS, SEED, digest, rows, read, write


def pilot():
    dest=OUT/'fallback_manifest.json'
    if not dest.exists():
        old_ids=['h003','h009','h012','h016','h030','h033','h083','h086','h126','h129','h139','h148','h171','h172','h027','h055','h079','h116','h153','h196']
        fresh=random.Random(SEED+2).sample([r['sample_id'] for r in rows()],20)
        write(dest,{'selection':'20 previously observed diagnostic failures plus 20 seeded fresh pages; same pages for both models', 'ids':old_ids+fresh})
    return read(dest)['ids']


def main():
    p=argparse.ArgumentParser();p.add_argument('method',choices=['mineru','olmocr']);p.add_argument('--limit',type=int);args=p.parse_args()
    import torch
    from transformers import AutoModelForImageTextToText,AutoProcessor,BitsAndBytesConfig
    torch.set_num_threads(4);torch.manual_seed(SEED)
    name='opendatalab/MinerU2.5-2509-1.2B' if args.method=='mineru' else 'allenai/olmOCR-2-7B-1025'
    path=read(OUT/'model_paths.json')[name]
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    started=time.perf_counter()
    kwargs={'torch_dtype':torch.bfloat16,'device_map':'cuda:0','attn_implementation':'sdpa','local_files_only':True}
    if args.method=='olmocr':
        kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True)
    model=AutoModelForImageTextToText.from_pretrained(path,**kwargs).eval()
    processor=AutoProcessor.from_pretrained(path,local_files_only=True)
    if args.method=='mineru':
        from mineru_vl_utils import MinerUClient
        client=MinerUClient(backend='transformers',model=model,processor=processor,batch_size=1,max_concurrency=1,use_tqdm=False,skip_model_name_checking=True)
    else:
        tree=ast.parse((OUT/'environment/olmocr_prompts.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_no_anchoring_v4_yaml_prompt')
        prompt=ast.literal_eval(next(n.value for n in fn.body if isinstance(n,ast.Return)))
    out=OUT/args.method
    write(out/'configuration.json',{'model':name,'revision':read(OUT/'model_revisions.json')[name],
        'dtype':'bf16' if args.method=='mineru' else 'NF4 double quantization / bf16 compute',
        'device':'RTX 3060 CUDA','max_new_tokens':4096 if args.method=='olmocr' else 'upstream defaults',
        'setup_seconds':time.perf_counter()-started,'implementation':'transformers direct; no upstream retry/rotation pipeline',
        'image_longest_edge':1288 if args.method=='olmocr' else '200 dpi native crops; 1036 layout thumbnail'})
    for sid in pilot()[:args.limit]:
        dest=out/(sid+'.json')
        if dest.exists():continue
        folder=(PREVIOUS if sid.startswith('h') else OUT)/'pages'/sid
        import pymupdf
        with pymupdf.open(folder/'page.pdf') as pdf:
            pg=pdf[0]; pix=pg.get_pixmap(dpi=200)
            img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        if args.method=='olmocr':img.thumbnail((1288,1288))
        started=time.perf_counter()
        try:
            with torch.inference_mode():
                if args.method=='mineru':
                    blocks=client.two_step_extract(img)
                    result={'blocks':[dict(b) if isinstance(b,dict) else vars(b) for b in blocks],'status':'success'}
                else:
                    messages=[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image','image':img}]}]
                    rendered=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                    inputs=processor(text=[rendered],images=[img],return_tensors='pt').to('cuda:0')
                    output=model.generate(**inputs,max_new_tokens=4096,do_sample=False)
                    generated=output[0,inputs['input_ids'].shape[1]:]
                    text=processor.decode(generated,skip_special_tokens=True)
                    result={'raw_text':text,'output_tokens':len(generated),'status':'success' if len(generated)<4096 else 'truncated'}
                    del inputs,output,generated
        except Exception as exc:
            result={'status':'error','error':type(exc).__name__+': '+str(exc)[:500]}
            torch.cuda.empty_cache()
        result.update(seconds=time.perf_counter()-started,page_sha256=digest(folder/'page.pdf'),sample_id=sid)
        write(dest,result)
        print({'processed':sid,'method':args.method,'seconds':round(result['seconds'],1),'state':result['status']},flush=True)


if __name__=='__main__':main()
