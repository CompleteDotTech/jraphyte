"""Wait for retained local outputs, then score and verify the complete experiment."""
import time
from .common import OUT, cache, rows, write


def main():
    started=time.monotonic(); previous=None
    while True:
        counts={method:sum(cache(method,r['sample_id']).exists() for r in rows()) for method in ['mineru','olmocr']}
        ready=(OUT/'retrieval_metrics.json').exists()
        state={**counts,'retrieval_complete':ready}
        if state!=previous:
            print(state,flush=True);write(OUT/'completion_progress.json',state);previous=state
        if all(n==200 for n in counts.values()) and ready:break
        if time.monotonic()-started>12*3600:
            raise TimeoutError('Local outputs incomplete after 12 hours; inspect worker logs')
        time.sleep(5)
    from .extraction import evaluate,METHODS
    from .verify import full
    from .report import main as report
    evaluate(METHODS)
    full()
    report()


if __name__=='__main__':
    main()
