"""Distinguish BF16 sequence-shape variation from incorrect causal positions."""
import json
import torch
from transformers import AutoModelForCausalLM
from common import ROOT,write_json
from score_worker import hidden


def main():
    row=json.loads((ROOT/'scoring_inputs.jsonl').open().readline())
    model=AutoModelForCausalLM.from_pretrained('/models/base',torch_dtype=torch.bfloat16,
        attn_implementation='flash_attention_2',local_files_only=True).to('cuda').eval()
    response=row['response_token_ids'];result={}
    with torch.inference_mode():
        for role in ['base','l3']:
            prompt=row['prompt_token_ids'] if role=='base' else row['teacher_prompt_token_ids'][role]
            h,ids=hidden(model,prompt,response)
            count=min(32,len(response));pos=min(3,count-1)
            chunks=model.lm_head(h[:count]).float()
            indices=torch.arange(len(prompt)-1,len(prompt)-1+count,device='cuda')
            native=model(input_ids=ids,use_cache=False,logits_to_keep=indices).logits[0].float()
            isolated=model(input_ids=torch.tensor([prompt+response[:pos]],device='cuda'),use_cache=False,logits_to_keep=1).logits[0,-1].float()
            modified=ids.clone();cutoff=len(prompt)+pos
            modified[:,cutoff:]=(modified[:,cutoff:]+1)%model.config.vocab_size
            future=model(input_ids=modified,use_cache=False,logits_to_keep=indices).logits[0,pos].float()
            lp=chunks[pos].double().log_softmax(-1);lq=isolated.double().log_softmax(-1)
            result[role]=dict(native_chunk_max_error=(native-chunks).abs().max().item(),
                isolated_prefix_max_logit_error=(isolated-chunks[pos]).abs().max().item(),
                isolated_prefix_KL=(lq.exp()*(lq-lp)).sum().item(),
                isolated_prefix_top1_agreement=bool(isolated.argmax()==chunks[pos].argmax()),
                same_shape_future_perturbation_max_error=(future-chunks[pos]).abs().max().item(),
                target_response_position=pos,prompt_length=len(prompt),response_length=len(response))
    write_json(ROOT/'prefix_alignment_probe.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
