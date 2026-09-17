"""Native CPU environments isolated from CUDA and Ray; line-delimited RPC."""
from pathlib import Path
import json
import os
import sys
import traceback
import textworld
from agent_system.environments.env_package.alfworld.alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos


def pack(state, score=0, done=False):
    return dict(observation=state.feedback.strip(), admissible_commands=list(state.admissible_commands),
                won=bool(state.won), lost=bool(state.lost), score=float(score), done=bool(done))


def main():
    envs = {}
    try:
        for line in sys.stdin:
            try:
                r = json.loads(line)
                if r['op'] == 'close':
                    break
                results = []
                if r['op'] == 'reset':
                    for item in r['items']:
                        env = textworld.start(str(Path(os.environ['ALFWORLD_DATA']) / item['gamefile']),
                            request_infos=textworld.EnvInfos(admissible_commands=True, won=True, lost=True),
                            wrappers=[AlfredDemangler(shuffle=False), AlfredInfos])
                        env.seed(42)
                        envs[item['sample_id']] = env
                        results.append(dict(sample_id=item['sample_id'], **pack(env.reset())))
                elif r['op'] == 'step':
                    for item in r['items']:
                        state, score, done = envs[item['sample_id']].step(item['command'])
                        results.append(dict(sample_id=item['sample_id'], **pack(state, score, done)))
                else:
                    raise ValueError(r['op'])
                print('@@ENV@@'+json.dumps(dict(ok=True, results=results)), flush=True)
            except Exception:
                print('@@ENV@@'+json.dumps(dict(ok=False, error=traceback.format_exc())), flush=True)
    finally:
        for env in envs.values():
            env.close()


if __name__ == '__main__':
    main()
