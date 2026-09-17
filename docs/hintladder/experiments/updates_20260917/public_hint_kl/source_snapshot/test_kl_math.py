import math
import unittest
import torch
from kl_math import compare_log_probs


class TestKL(unittest.TestCase):
    def test_known_asymmetric_distributions(self):
        p=torch.tensor([[.8,.1,.1]],dtype=torch.float64)
        q=torch.tensor([[.2,.3,.5]],dtype=torch.float64)
        result=compare_log_probs(p.log(),q.log(),torch.tensor([[2]]))
        expected=sum(qv*math.log(qv/pv) for pv,qv in zip(p[0].tolist(),q[0].tolist()))
        reverse=sum(pv*math.log(pv/qv) for pv,qv in zip(p[0].tolist(),q[0].tolist()))
        self.assertAlmostEqual(result['forward_full'].item(),expected,places=12)
        self.assertAlmostEqual(result['reverse_full'].item(),reverse,places=12)
        self.assertNotAlmostEqual(expected,reverse)
        coarse=.5*math.log(.5/.1)+.5*math.log(.5/.9)
        self.assertAlmostEqual(result['forward_top32_tail'].item(),coarse,places=12)
        self.assertLessEqual(coarse,expected)

    def test_identical_distributions_zero_including_tail(self):
        torch.manual_seed(42)
        logits=torch.randn(4,128,dtype=torch.float64)
        lp=logits.log_softmax(-1)
        result=compare_log_probs(lp,lp,logits.topk(32,dim=-1).indices)
        for key in ['forward_full','reverse_full','forward_top32_tail','reverse_top32_tail']:
            self.assertTrue(torch.equal(result[key],torch.zeros(4,dtype=torch.float64)))

    def test_tiny_tail_stays_finite_and_coarsening_lowers_kl(self):
        a=torch.linspace(-150,10,128,dtype=torch.float32)[None]
        b=a.flip(-1)
        result=compare_log_probs(a.log_softmax(-1),b.log_softmax(-1),b.topk(32,-1).indices)
        for value in result.values():self.assertTrue(torch.isfinite(value).all())
        self.assertLessEqual(result['forward_top32_tail'].item(),result['forward_full'].item()+1e-5)


if __name__=='__main__':unittest.main()
