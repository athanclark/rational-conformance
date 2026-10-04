"""Backend-independent exact oracle. Integers never pass through floating point."""
from fractions import Fraction as Q
import random

def canonical(q):
    return f"{q.numerator}/{q.denominator}"

def parse(text):
    n, _, d = text.partition("/")
    return Q(int(n), int(d) if d else 1)

def fixture():
    rng = random.Random(9421)
    offset, scale = 10**1200, 10**1100
    points = {Q(k, 10): rng.randrange(1, 8) for k in [-100, -9, -4, 0, 4, 8, 12, 20, 21, 22, 50]}
    points.update({Q(offset * scale + k, scale): k + 1 for k in range(12)})
    # All implementations must replace the weight at numerically equal coordinates.
    writes = [[canonical(q), str(w)] for q, w in points.items()]
    writes += [["8/20", "11"], ["0/-99", "3"]]
    for key, weight in writes:
        points[parse(key)] = int(weight)
    queries = []
    bounds = [(None, None), ("-1", "3"), ("2/5", "2/5"), ("3", "-1"),
              (str(offset), canonical(Q(offset * scale + 12, scale)))]
    for lo, hi in bounds:
        for threshold in ["0", "2/5", "1", canonical(Q(4, scale))]:
            for mode in ["span", "neighbors"]:
                for il, iu in [(True, False), (False, True), (True, True), (False, False)]:
                    queries.append(dict(lower=lo, upper=hi, threshold=threshold,
                                        mode=mode, includeLower=il, includeUpper=iu))
    arithmetic = [["2/4", "-6/-8"], [str(offset), canonical(Q(1, scale))]]
    for _ in range(40):
        arithmetic.append([canonical(Q(rng.randrange(-10**100, 10**100), rng.randrange(1, 10**70))),
                           canonical(Q(rng.randrange(1, 10**90), rng.randrange(1, 10**50)))])
    return dict(version=1, writes=writes, queries=queries, arithmetic=arithmetic)

def oracle(data):
    points = {parse(k): int(w) for k, w in data["writes"]}
    answers = []
    for query in data["queries"]:
        lo = Q(query["lower"]) if query["lower"] is not None else None
        hi = Q(query["upper"]) if query["upper"] is not None else None
        threshold = Q(query["threshold"])
        rows, groups = [], []
        for key, weight in sorted(points.items()):
            if lo is not None and (key < lo or key == lo and not query["includeLower"]):
                continue
            if hi is not None and (key > hi or key == hi and not query["includeUpper"]):
                continue
            rows.append([canonical(key), str(weight)])
            previous = groups[-1] if groups else None
            anchor = previous[1 if query["mode"] == "neighbors" else 0] if previous else None
            if previous and key - anchor < threshold:
                previous[4] = max(previous[4], key - previous[1])
                previous[1], previous[2], previous[3] = key, previous[2] + weight, previous[3] + 1
            else:
                groups.append([key, key, weight, 1, Q(0)])
        answers.append(dict(rows=rows, groups=[
            [canonical(a), canonical(b), str(n), str(k), canonical(g)] for a, b, n, k, g in groups]))
    arithmetic = []
    for sa, sb in data["arithmetic"]:
        a, b = parse(sa), parse(sb)
        arithmetic.append([canonical(a), canonical(b), str((a > b) - (a < b)),
                           *map(canonical, [a+b, a-b, a*b, a/b])])
    return dict(queries=answers, arithmetic=arithmetic)
