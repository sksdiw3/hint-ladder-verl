"""Score all vocabularies on Base's ORIGINAL sampled prefixes, with no updates."""
import argparse
from collections import defaultdict
import gzip
import json
import time
import traceback
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from common import ROOT,read_jsonl,write_json
from kl_math import compare_log_probs,position_regions

LEVELS=['l1','l2','l3']
TEMPERATURES=[1.0,0.6]
CHUNK=32


def hidden(model,prompt,response):
    # Position len(prompt)-1 predicts response[0]; position len(prompt)+i-1
    # predicts response[i], conditioned on exactly response[:i].
    ids=torch.tensor([prompt+response[:-1]],device='cuda')
    h=model.model(input_ids=ids,use_cache=False,return_dict=True).last_hidden_state
    return h[0,len(prompt)-1:len(prompt)-1+len(response)],ids


def main(worker):
    torch.set_num_threads(2)
    started=time.monotonic();folder=ROOT/'scores';folder.mkdir(exist_ok=True)
    if (folder/f'complete_{worker}.json').exists():return
    rows=[row for row in read_jsonl(ROOT/'scoring_inputs.jsonl') if row['score_row_index']%8==worker]
    tok=AutoTokenizer.from_pretrained('/models/base',local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained('/models/base',torch_dtype=torch.bfloat16,
        attn_implementation='flash_attention_2',local_files_only=True).to('cuda').eval()
    count=0;checks=dict(vocabulary_size=model.get_output_embeddings().weight.shape[0],
        model_training_mode=model.training,temperatures=TEMPERATURES,logits_chunk_size=CHUNK);min_kl=0.0
    try:
        with torch.inference_mode(),gzip.open(folder/f'tokens_{worker}.jsonl.gz','wt',compresslevel=3) as stream, \
             (folder/f'turns_{worker}.jsonl').open('w',buffering=1) as turnstream:
            for ri,row in enumerate(rows):
                response=row['response_token_ids'];n=len(response)
                assert n>0
                regions=position_regions(tok,response)
                hs={};hs['base'],full_ids=hidden(model,row['prompt_token_ids'],response)
                for level in LEVELS:
                    hs[level],_=hidden(model,row['teacher_prompt_token_ids'][level],response)
                assert all(h.shape[0]==n for h in hs.values())
                turnagg=defaultdict(lambda:defaultdict(float))
                for start in range(0,n,CHUNK):
                    stop=min(n,start+CHUNK)
                    logits={role:model.lm_head(h[start:stop]).float() for role,h in hs.items()}
                    targets=torch.tensor(response[start:stop],device='cuda')
                    if ri==0 and start==0:
                        indices=torch.arange(len(row['prompt_token_ids'])-1,len(row['prompt_token_ids'])-1+stop,device='cuda')
                        native=model(input_ids=full_ids,use_cache=False,logits_to_keep=indices).logits[0].float()
                        err=(native-logits['base']).abs().max().item()
                        checks['native_forward_max_logit_error']=err
                        assert err<1e-6,err
                        for level in ['base','l3']:
                            prompt=row['prompt_token_ids'] if level=='base' else row['teacher_prompt_token_ids'][level]
                            pos=min(17,stop-1)
                            isolated=model(input_ids=torch.tensor([prompt+response[:pos]],device='cuda'),use_cache=False,logits_to_keep=1).logits[0,-1].float()
                            error=(isolated-logits[level][pos]).abs().max().item()
                            checks[f'isolated_prefix_max_logit_error_{level}']=error
                            pl=logits[level][pos].double().log_softmax(-1)
                            ql=isolated.double().log_softmax(-1)
                            checks[f'isolated_prefix_distribution_kl_{level}']=(ql.exp()*(ql-pl)).sum().item()
                            # A different sequence length can select a different
                            # BF16 kernel. Test causal alignment at SAME shape:
                            # perturb every token after the tested prefix.
                            full=torch.tensor([prompt+response[:-1]],device='cuda')
                            cutoff=len(prompt)+pos
                            full[:,cutoff:]=(full[:,cutoff:]+1)%model.config.vocab_size
                            indices=torch.arange(len(prompt)-1,len(prompt)-1+stop,device='cuda')
                            causal=model(input_ids=full,use_cache=False,logits_to_keep=indices).logits[0,pos].float()
                            causal_error=(causal-logits[level][pos]).abs().max().item()
                            checks[f'future_token_perturbation_max_logit_error_{level}']=causal_error
                            assert causal_error<1e-6,(level,causal_error)
                    top32={role:values.topk(32,dim=-1).indices for role,values in logits.items()}
                    overlap={level:(top32['base'][:,:,None]==top32[level][:,None,:]).any(-1).sum(-1).tolist() for level in LEVELS}
                    changed={level:(logits['base'].argmax(-1)!=logits[level].argmax(-1)).tolist() for level in LEVELS}
                    calculated={}
                    for temperature in TEMPERATURES:
                        logs={role:torch.log_softmax(values/temperature,-1) for role,values in logits.items()}
                        calculated[str(temperature)]={}
                        for level in LEVELS:
                            metrics=compare_log_probs(logs['base'],logs[level],top32[level])
                            metrics['base_target_logp']=logs['base'].gather(-1,targets[:,None])[:,0]
                            metrics['hint_target_logp']=logs[level].gather(-1,targets[:,None])[:,0]
                            for field in ['forward_full','reverse_full','forward_top32_tail','reverse_top32_tail']:
                                assert torch.isfinite(metrics[field]).all()
                                minimum=metrics[field].min().item();min_kl=min(min_kl,minimum)
                                assert minimum>-2e-5,(row['row_id'],field,minimum)
                            assert (metrics['forward_full']-metrics['forward_top32_tail']).min().item()>-2e-5
                            if ri==0 and start==0:
                                pl=torch.log_softmax(logits['base'][0].double()/temperature,-1)
                                ql=torch.log_softmax(logits[level][0].double()/temperature,-1)
                                reference=(ql.exp()*(ql-pl)).sum().item()
                                error=abs(reference-metrics['forward_full'][0].item())
                                checks[f'fp64_kl_error_{level}_T{temperature}']=error
                                assert error<2e-5,error
                            calculated[str(temperature)][level]={key:value.tolist() for key,value in metrics.items()}
                    for j in range(stop-start):
                        position=start+j;region=regions[position]
                        scopes=['all_response',region]
                        if region=='reasoning_body' and not row['format_error']:scopes.append('valid_reasoning_body')
                        entry=dict(row_id=row['row_id'],score_row_index=row['score_row_index'],
                            sample_id=row['sample_id'],cohort=row['cohort'],split=row['split'],turn=row['turn'],
                            response_index=position,prefix_token_count=position,region=region,
                            actual_next_token_id=response[position],
                            actual_next_token_text=tok.decode([response[position]],skip_special_tokens=False,clean_up_tokenization_spaces=False),
                            metrics={temp:{level:{k:v[j] for k,v in values.items()}
                                for level,values in levels.items()} for temp,levels in calculated.items()},
                            overlap_top32={level:overlap[level][j] for level in LEVELS},
                            top1_changed={level:changed[level][j] for level in LEVELS})
                        stream.write(json.dumps(entry,ensure_ascii=False,allow_nan=False)+'\n')
                        for temp,levels in entry['metrics'].items():
                            for level,metrics in levels.items():
                                for scope in scopes:
                                    acc=turnagg[f'{scope}|{level}|{temp}'];acc['count']+=1
                                    for name,value in metrics.items():acc[name]+=value
                                    acc['overlap_top32']+=entry['overlap_top32'][level]
                                    acc['top1_changed']+=int(entry['top1_changed'][level])
                    count+=stop-start
                    del logits,logs,calculated
                summary=dict(row_id=row['row_id'],score_row_index=row['score_row_index'],
                    sample_id=row['sample_id'],cohort=row['cohort'],split=row['split'],turn=row['turn'],
                    task=row['task'],format_error=row['format_error'],response_tokens=n,
                    statistics={key:dict(count=int(acc['count']),**{k:v/acc['count'] for k,v in acc.items() if k!='count'}) for key,acc in turnagg.items()})
                turnstream.write(json.dumps(summary,ensure_ascii=False,allow_nan=False)+'\n')
                write_json(folder/f'progress_{worker}.json',dict(worker=worker,completed_turns=ri+1,total_turns=len(rows),positions=count,seconds=time.monotonic()-started))
                if (ri+1)%20==0 or ri+1==len(rows):print(json.dumps(dict(worker=worker,turns=ri+1,total=len(rows),positions=count)),flush=True)
                del hs,full_ids
        write_json(folder/f'complete_{worker}.json',dict(worker=worker,turns=len(rows),positions=count,
            seconds=time.monotonic()-started,peak_allocated_bytes=torch.cuda.max_memory_allocated(),checks=checks,min_raw_kl=min_kl))
    except Exception:
        write_json(folder/f'error_{worker}.json',dict(error=traceback.format_exc()))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=int,required=True)
    main(parser.parse_args().worker)
