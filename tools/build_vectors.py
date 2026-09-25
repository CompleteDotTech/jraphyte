#!/usr/bin/env python3
"""Publish transport/canonical bytes/hash vectors for independent implementations."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trace_gc.canonical import canonical_bytes,digest,write

def main():
    cases=[("null",None),("true",True),("false",False),("integer-zero",0),("integer-one",1),
           ("float-one",1.0),("negative-float-zero",-0.0),("positive-float-zero",0.0),
           ("max-integer",2**53-1),("min-integer",-(2**53-1)),("tiny-float",1e-20),
           ("unicode","雪😀é"),("decomposed-unicode","e\u0301"),("empty-array",[]),("empty-object",{}),
           ("ordered-array",[None,True,1,1.0,"x"]),("utf8-sorted-keys",{"é":1,"a":2,"😀":3}),
           ("nested",{"a":[{"b":-7}],"empty":""})]
    result={"profile":"TRACE-C14N-1","hash":"SHA-256","valid":[{"name":n,"value":v,"canonical_hex":canonical_bytes(v).hex(),"sha256":digest(v)} for n,v in cases],
            "invalid_json":[{"text":text,"expected_code":code} for text,code in [('{"x":1,"x":2}',"DUPLICATE_JSON_KEY"),("NaN","NONFINITE_JSON"),("Infinity","NONFINITE_JSON"),("1e400","NONFINITE_JSON"),("9007199254740992","INTEGER_RANGE"),('"\\ud800"',"INVALID_UNICODE")]]}
    target=ROOT/"examples/runtime/canonical_vectors.json";write(target,result)
    print(f"Wrote {len(cases)} valid and {len(result['invalid_json'])} invalid canonical vectors")
if __name__=="__main__":main()
