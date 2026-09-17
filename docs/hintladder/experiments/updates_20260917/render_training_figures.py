"""Plot archived numeric logs only; never launch inference or training."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent / 'frozen_teacher_training'


def load(name):
    return [json.loads(x) for x in (ROOT/name).read_text().splitlines()]


def main():
    runs = {'Frozen L1': load('l1_metrics.jsonl'),
            'Frozen Oracle L3': load('l3_effective_metrics.jsonl'),
            'Moving-teacher L1 (historical)': load('historical_moving_teacher_metrics.jsonl')}
    colors = {'Frozen L1': '#246aaf', 'Frozen Oracle L3': '#cc7621',
              'Moving-teacher L1 (historical)': '#878b94'}
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.6), layout='constrained')
    for ax, split, denom in zip(axes[0], ['valid_seen','valid_unseen'], [140,134]):
        for label, rows in list(runs.items())[:2]:
            es = [r for r in rows if f'val/{split}/success_rate' in r]
            ax.plot([r['step'] for r in es],
                    [100*r[f'val/{split}/text/success/mean@1'] for r in es],
                    marker='o', lw=2, color=colors[label], label=label)
        ax.set_title(f"{'Seen' if split == 'valid_seen' else 'Unseen'}: {denom} games, no hints")
        ax.set_ylabel('Success rate (%)')
        ax.set_ylim(0,60)
        ax.set_xlabel('Evaluated checkpoint step')
        ax.set_xticks([25,50,75,100,125,150])
        ax.legend(fontsize=9, loc='lower right')
    for label, rows in runs.items():
        style = '--' if label.startswith('Moving') else '-'
        axes[1,0].plot([r['step'] for r in rows], [r['response_length/mean'] for r in rows],
                       color=colors[label], lw=1.5, ls=style, label=label)
        axes[1,1].plot([r['step'] for r in rows],
                       [100*r['hint_ladder/format_invalid_ratio'] for r in rows],
                       color=colors[label], lw=1.5, ls=style, label=label)
    axes[1,0].set_title('Training rollout response length (before update)')
    axes[1,0].set_ylabel('Tokens / response (includes tags and action)')
    axes[1,1].set_title('Format-invalid turns (includes empty reasoning)')
    axes[1,1].set_ylabel('Format-invalid turns (%)')
    axes[1,1].set_ylim(-3,103)
    for ax in axes[1]:
        ax.set_xlabel('Recorded training step')
        ax.legend(fontsize=8, loc='best')
    for ax in axes.flat:
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('ALFWorld OPD: frozen Base teachers and the historical moving teacher', fontsize=15)
    fig.savefig(ROOT/'training_curves.png', dpi=180)
    fig.savefig(ROOT/'training_curves.pdf')


if __name__ == '__main__':
    main()
