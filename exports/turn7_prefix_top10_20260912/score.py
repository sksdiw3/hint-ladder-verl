"""Frozen-base top-10 for every prediction prefix of one retained full turn."""
import hashlib
import json
from pathlib import Path
import re
import time
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from hintladder.teacher_prompt import insert_note,remove_note

ROOT=Path(__file__).resolve().parent
SOURCE=Path('exports/key_error_traces_20260912')
started=time.monotonic()
torch.set_num_threads(2)
tok=AutoTokenizer.from_pretrained('/models/Qwen3-4B',local_files_only=True)
identity=json.loads((SOURCE/'base_identity/model_identity.json').read_text())
for field,name in [('tokenizer_sha256','tokenizer.json'),('model_config_sha256','config.json')]:
    assert hashlib.sha256((Path('/models/Qwen3-4B')/name).read_bytes()).hexdigest()==identity[field]
for f in identity['weight_files']:assert (Path('/models/Qwen3-4B')/f['file']).stat().st_size==f['bytes']
src=next(r for r in map(json.loads,(SOURCE/'distribution_example_prompts.jsonl').open()) if r['pair_id']==7)
episode=next(r['original'] for r in map(json.loads,(SOURCE/'base_matched_controls.jsonl').open())
             if r['original']['pair_id']==7 and r['original']['arm']=='no_hint')
turn=episode['turns'][0]
assert src['checkpoint_step']==0 and src['response_ids']==turn['response_token_ids']
student=src['student_prompt'];teacher=insert_note(student,src['hint'])
assert remove_note(teacher)==student and teacher==src['teacher_prompt']
assert tok.encode(student,add_special_tokens=False)==src['student_prompt_ids']
assert tok.encode(teacher,add_special_tokens=False)==src['teacher_prompt_ids']
response=src['response_ids'];n=len(response)
assert n==105
raw=tok.decode(response,skip_special_tokens=False,clean_up_tokenization_spaces=False)
prefixes=[tok.decode(response[:i],skip_special_tokens=False,clean_up_tokenization_spaces=False) for i in range(n+1)]
assert all(prefixes[i+1].startswith(prefixes[i]) for i in range(n))
model=AutoModelForCausalLM.from_pretrained('/models/Qwen3-4B',torch_dtype=torch.bfloat16,
    attn_implementation='flash_attention_2',local_files_only=True).to('cuda').eval()
data={'student':[],'teacher':[]};checks=[]
with torch.inference_mode():
    for arm,prompt in [('student',src['student_prompt_ids']),('teacher',src['teacher_prompt_ids'])]:
        ids=torch.tensor([prompt+response[:-1]],device='cuda')
        indices=torch.arange(len(prompt)-1,len(prompt)+n-1,device='cuda')
        hidden=model.model(input_ids=ids,use_cache=False,return_dict=True).last_hidden_state[0].index_select(0,indices)
        for start in range(0,n,32):
            logits=model.lm_head(hidden[start:start+32]).float()
            values,topids=logits.topk(10,dim=-1)
            boundary=logits.topk(11,dim=-1).values
            vals=values.tolist();tids=topids.tolist()
            per_temperature={}
            for temp in [0.6,1.0]:
                lp=torch.log_softmax(logits/temp,dim=-1);p=lp.exp()
                targets=torch.tensor(response[start:start+len(logits)],device='cuda')
                per_temperature[str(temp)]={
                    'probabilities':lp.gather(-1,topids).exp().tolist(),
                    'log_probabilities':lp.gather(-1,topids).tolist(),
                    'entropy_nats':(-(p*lp).sum(-1)).tolist(),
                    'target_probability':lp.gather(-1,targets[:,None]).exp()[:,0].tolist(),
                    'top10_mass':lp.gather(-1,topids).exp().sum(-1).tolist()}
            for j in range(len(logits)):
                i=start+j
                data[arm].append({'top10':[{'rank':rank+1,'id':tid,'text':tok.decode([tid],skip_special_tokens=False,clean_up_tokenization_spaces=False),
                    'raw_logit':vals[j][rank],
                    'probability':{t:d['probabilities'][j][rank] for t,d in per_temperature.items()},
                    'log_probability':{t:d['log_probabilities'][j][rank] for t,d in per_temperature.items()}}
                    for rank,tid in enumerate(tids[j])],
                    'entropy_nats':{t:d['entropy_nats'][j] for t,d in per_temperature.items()},
                    'target_probability':{t:d['target_probability'][j] for t,d in per_temperature.items()},
                    'target_rank':int((logits[j]>logits[j,response[i]]).sum().item()+1),
                    'top10_mass':{t:d['top10_mass'][j] for t,d in per_temperature.items()},
                    'rank10_11_tie':bool(boundary[j,9]==boundary[j,10])})
                # Different input lengths independently check causal alignment.
                if i in [0,4,30,60,n-1]:
                    truncated=torch.tensor([prompt+response[:i]],device='cuda')
                    check=model(input_ids=truncated,use_cache=False,logits_to_keep=1).logits[0,0].float()
                    err=(check-logits[j]).abs().max().item()
                    delta=(check.softmax(-1)-logits[j].softmax(-1)).abs().max().item()
                    checks.append({'arm':arm,'response_index':i,'max_abs_logit_difference':err,'max_abs_probability_difference_T1':delta})
                    assert err<0.6 and delta<0.03,(arm,i,err,delta)
        print(json.dumps({'arm':arm,'scored_positions':len(data[arm])}),flush=True)

tags=[(m.start(),m.end(),m.group()) for m in re.finditer(r'</?reasoning>|</?action>',raw)]
def region(i):
    if response[i] in tok.all_special_ids:return '结束 token'
    a,b=len(prefixes[i]),len(prefixes[i+1])
    if i in src['body_positions']:return 'reasoning 正文'
    for x,y,label in tags:
        if a<y and b>x:return label+' 标签/边界'
    am=re.search(r'<action>(.*?)</action>',raw,re.S)
    if am and a>=am.start(1) and b<=am.end(1):return 'action 正文'
    return '空白/边界'
records=[]
for i in range(n):
    s,t=data['student'][i],data['teacher'][i]
    shared=sorted(set(x['id'] for x in s['top10'])&set(x['id'] for x in t['top10']))
    records.append({'position':i+1,'response_index':i,'prefix_token_count':i,'response_prefix':prefixes[i],
        'actual_next_token':{'id':response[i],'text':tok.decode([response[i]],skip_special_tokens=False,clean_up_tokenization_spaces=False),
                             'decoded_increment':prefixes[i+1][len(prefixes[i]):]},
        'region':region(i),'is_reasoning_body':i in src['body_positions'],
        'student':s,'teacher':t,'top10_shared_ids':shared,'top10_overlap_count':len(shared)})
assert len(records)==n and [r['response_index'] for r in records]==list(range(n))
metadata={'model':'Original Qwen3-4B','checkpoint_step':0,'split':'train','pair_id':7,'turn':1,'task':src['task'],
    'task_zh':'找到洗手液瓶，放到马桶上。','hint':src['hint'],
    'hint_zh':'洗手液通常放在洗手的地方，先检查浴室里可见的台面，再考虑翻抽屉。找到后需要先拿起来，才能放到新的位置。',
    'student_prompt':student,'teacher_prompt':teacher,'response_ids':response,'raw_response':raw,'response':src['output'],
    'current_observation':turn.get('observation'),'admissible_actions':turn.get('admissible_commands'),
    'executed_action':turn.get('executed_action'),'next_state':turn.get('next_state'),
    'response_positions':n,'reasoning_body_positions':len(src['body_positions']),
    'temperatures':[0.6,1.0],'softmax':'Full vocabulary, no top-k/top-p truncation or within-top10 renormalization',
    'top_k':10,'teacher_condition':'Current student prompt + cached hint and advisory; identical original student response prefix',
    'weights_dtype':'bfloat16','probability_dtype':'float32','attention':'flash_attention_2','gpu':7,
    'source_files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE/'distribution_example_prompts.jsonl',SOURCE/'base_matched_controls.jsonl']},
    'model_identity':identity,'checks':checks,'seconds_including_load':time.monotonic()-started,
    'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'new_rollouts':0,'api_calls':0,'weight_updates':0}
(ROOT/'turn.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
(ROOT/'prefix_top10.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records))
print(json.dumps({'complete':True,'positions':n,'body_positions':len(src['body_positions']),'seconds':metadata['seconds_including_load'],'peak_GiB':metadata['peak_allocated_bytes']/1024**3}),flush=True)
