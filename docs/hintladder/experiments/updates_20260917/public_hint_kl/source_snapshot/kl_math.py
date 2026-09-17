"""Exact full-vocabulary and coarsened Top-K-plus-tail categorical KL."""
import re
import torch


def compare_log_probs(log_p,log_q,q_indices):
    p,q=log_p.exp(),log_q.exp()
    forward=(q*(log_q-log_p)).sum(-1)
    reverse=(p*(log_p-log_q)).sum(-1)
    qsel=log_q.gather(-1,q_indices)
    psel=log_p.gather(-1,q_indices)
    qoutside=log_q.clone().scatter_(-1,q_indices,float('-inf'))
    poutside=log_p.clone().scatter_(-1,q_indices,float('-inf'))
    lqt=torch.logsumexp(qoutside,dim=-1)
    lpt=torch.logsumexp(poutside,dim=-1)
    coarse=(qsel.exp()*(qsel-psel)).sum(-1)+lqt.exp()*(lqt-lpt)
    reverse_coarse=(psel.exp()*(psel-qsel)).sum(-1)+lpt.exp()*(lpt-lqt)
    return dict(forward_full=forward,reverse_full=reverse,
        forward_top32_tail=coarse,reverse_top32_tail=reverse_coarse,
        base_entropy=-(p*log_p).sum(-1),hint_entropy=-(q*log_q).sum(-1),
        base_top1=p.max(-1).values,hint_top1=q.max(-1).values,
        base_mass_on_hint_top32=psel.exp().sum(-1),hint_top32_mass=qsel.exp().sum(-1))


def position_regions(tokenizer,ids):
    raw=tokenizer.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
    prefixes=[tokenizer.decode(ids[:i],skip_special_tokens=False,clean_up_tokenization_spaces=False) for i in range(len(ids)+1)]
    opening=re.search(r'<reasoning>',raw,re.I);closing=re.search(r'</reasoning>',raw,re.I)
    action=re.search(r'<action>(.*?)</action>',raw,re.S|re.I)
    tags=list(re.finditer(r'</?reasoning>|</?action>',raw,re.I))
    regions=[]
    for i,token in enumerate(ids):
        a,b=len(prefixes[i]),len(prefixes[i+1])
        if token in tokenizer.all_special_ids:region='special'
        elif any(a<m.end() and b>m.start() for m in tags):
            region='reasoning_close_tag' if closing and a<closing.end() and b>closing.start() else 'tag_or_boundary'
        elif opening and closing and a>=opening.end() and b<=closing.start():region='reasoning_body'
        elif action and a>=action.start(1) and b<=action.end(1):region='action_body'
        elif opening and closing is None and a>=opening.end():region='unclosed_reasoning_or_following_text'
        else:region='other'
        regions.append(region)
    return regions
