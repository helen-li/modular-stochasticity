# Eval file

import argparse
import torch
import torch.nn as nn
import random
import numpy as np
import os

from data import rules
from model import Model

parser = argparse.ArgumentParser(description='Rule MLP')
parser.add_argument('--search-version', type=int, default=1, choices=(1,2))
parser.add_argument('--gt-rules', type=int, default=2)
parser.add_argument('--data-seed', type=int, default=0)
parser.add_argument('--seq-len', type=int, default=10)

parser.add_argument('--batch-size', type=int, default=1000)
parser.add_argument('--lr', type=float, default=0.0001)
parser.add_argument('--iterations', type=int, default=200000)

parser.add_argument('--dim', type=int, default=128)
parser.add_argument('--att-dim', type=int, default=512)
parser.add_argument('--model', type=str, default='Monolithic', choices=('Monolithic', 'Modular', 'GT_Modular'))
parser.add_argument('--num-heads', type=int, default=2)
parser.add_argument('--num-rules', type=int, default=2)
parser.add_argument('--op', action='store_true', default=False)

parser.add_argument('--scheduler', action='store_true', default=False)
parser.add_argument('--best', action='store_true', default=False)
parser.add_argument('--seed', type=int, default=0)
args = parser.parse_args()

def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(seed)

def slow_exit():
    import time
    time.sleep(1)
    exit()

set_seed(args.seed)

def eval_step(eval_len=args.seq_len, ood=False, n_evals=100):
    model.eval()
    total_loss = 0.
    total_acc = 0.

    with torch.no_grad():
        for _ in range(n_evals):
            data, label, op = rules(args.batch_size, eval_len, args.gt_rules, 2, \
                                args.search_version, args.data_seed, ood)

            data = torch.Tensor(data).to(device)
            label = torch.Tensor(label).to(device)
            op = torch.Tensor(op).to(device)

            out, score = model(data, op)

            loss = criterion(out, label)
            acc = torch.eq(out >= 0., label).double().mean()

            total_loss += loss.item()
            total_acc += acc.item()

            del data, label, op

    return total_loss / float(n_evals), total_acc * 100. / float(n_evals)

if args.seq_len == 10:
    test_lens = [3, 5, 10, 20, 30]
else:
    test_lens = [10, 20, 30, 40, 50]

device = torch.device('cuda')

if args.op:
    extras = f'_operation-only_'
else:
    extras = '_'

if args.scheduler:
    ext='_scheduler'
else:
    ext=''

name = f'Sequence_{args.seq_len}{ext}/Search-Version_{args.search_version}/Data-Seed_{args.data_seed}/GT_Rules_{args.gt_rules}/{args.model}{extras}{args.dim}_{args.att_dim}_{args.num_heads}_{args.num_rules}_{args.seed}'

if args.best:
    ckpt = '_best'
else:
    ckpt = '_last'

if not os.path.exists(name):
    print(name)
    print('Model not found')
    slow_exit()
else:
    if not os.path.exists(f'{name}/loss.png'):
        print('Incomplete Model Training')
        slow_exit()

    if os.path.exists(f'{name}/perf{ckpt}.txt'):
        print('Performance Computed Already')
        slow_exit()

if args.search_version == 1:
    in_dim = args.num_rules * 5
elif args.search_version == 2:
    in_dim = args.num_rules * 7
else:
    print("Search Version Not Supported")
    slow_exit()

model = Model(
    dim = args.dim,
    att_dim = args.att_dim,
    num_heads = args.num_heads,
    in_dim = in_dim,
    model = args.model,
    num_rules = args.num_rules,
    op = args.op
).to(device)

print('Loading Model')
model.load_state_dict(torch.load(f'{name}/model{ckpt}.pt'))
criterion = nn.BCEWithLogitsLoss()

gt_ticks = [f'Ground Truth Rule {i}' for i in range(1, args.gt_rules+1)]

num_params = sum(p.numel() for p in model.parameters())
print(model)
print(f"Number of Parameters: {num_params}")

# Compute Performance

eval_log = f'Iteration: 0 | '
eval_ood_log = f'Iteration: 0 | '

for seq_len in test_lens:
    eval_loss, eval_acc = eval_step(seq_len)
    eval_ood_loss, eval_ood_acc = eval_step(seq_len, True)

    eval_log += f'Seq. Len: {seq_len} - Final Eval Loss: {eval_loss} - Final Eval Acc: {eval_acc} | '
    eval_ood_log += f'Seq. Len: {seq_len} - Final Eval OoD Loss: {eval_ood_loss} - Final Eval OoD Acc: {eval_ood_acc} | '

log = eval_log + '\n' + eval_ood_log + '\n'

print(log)
with open(os.path.join(name, f'perf{ckpt}.txt'), 'w') as f:
    f.write(log)