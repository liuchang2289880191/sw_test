"""Read-only geometry checks; this does not generate or submit hardware cases."""
import json
from itertools import product
import numpy as np
from generate_plan import features, member


def matrix(probes, adjacent):
    rows = []
    for ps, pd in probes:
        for bs, bd in product(range(16), repeat=2):
            if bs == bd or {bs, bd} & {ps, pd}:
                continue
            if adjacent and abs(bs//4-bd//4)+abs(bs%4-bd%4) != 1:
                continue
            feat = features((member(ps), member(pd)), (member(bs), member(bd)))
            for large in (0, 1):
                rows.append([1, large, *feat.values()])
    return np.asarray(rows)


def main():
    for label, probes, adjacent in [
        ('two_probe_directions_adjacent_background', [(0,15),(15,0)], True),
        ('four_probe_directions_adjacent_background', [(0,15),(3,12),(12,3),(15,0)], True),
        ('two_probe_directions_all_background_pairs', [(0,15),(15,0)], False),
        ('all_probe_directions_all_background_pairs', [(s,d) for s,d in product(range(16),repeat=2) if s!=d], False),
    ]:
        x = matrix(probes, adjacent)
        print(json.dumps(dict(design=label, rows=x.shape[0], columns=x.shape[1], rank=int(np.linalg.matrix_rank(x)))))
    print(json.dumps(features((member(0),member(15)),(member(1),member(6)))))


if __name__ == '__main__':
    main()
