import argparse
import json
import os
import subprocess
import sys
import time
from common import ROOT, write_json


def main(phase):
    logdir=ROOT/'logs';logdir.mkdir(exist_ok=True)
    jobs=[];started=time.monotonic()
    try:
        for worker in range(8):
            log=(logdir/f'{phase}_{worker}.log').open('a')
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(worker),OMP_NUM_THREADS='2',
                     OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',TOKENIZERS_PARALLELISM='false')
            p=subprocess.Popen([sys.executable,'-u',str(ROOT/f'{phase}_worker.py'),'--worker',str(worker)],
                               env=env,stdout=log,stderr=subprocess.STDOUT)
            jobs.append((worker,p,log))
        while any(p.poll() is None for _,p,_ in jobs):
            failed=[(w,p.returncode) for w,p,_ in jobs if p.poll() not in (None,0)]
            if failed:
                raise RuntimeError(f'{phase} worker failures: {failed}')
            time.sleep(2)
        assert all(p.returncode==0 for _,p,_ in jobs)
        write_json(ROOT/f'{phase}_complete.json',dict(workers=8,seconds=time.monotonic()-started))
    finally:
        for _,p,_ in jobs:
            if p.poll() is None:p.terminate()
        for _,p,log in jobs:
            try:p.wait(timeout=30)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['rollout','score'],required=True)
    main(p.parse_args().phase)
