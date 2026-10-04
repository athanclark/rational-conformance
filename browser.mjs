import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
const entry = process.argv[2]
  ? pathToFileURL(resolve(process.argv[2]))
  : new URL("../rational-map/dist/index.js", import.meta.url);
const { Rational: Q, RationalMap } = await import(entry.href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const data = JSON.parse(input);
const map = new RationalMap(v => v);
for (const [key, weight] of data.writes) map.set(Q.parse(key), BigInt(weight));
const bound = q => q === null ? undefined : Q.parse(q);
const queries = data.queries.map(query => {
  const lo = bound(query.lower), hi = bound(query.upper);
  return {
    rows: [...map.range(lo, hi, query)].map(([k, v]) => [k.toString(), v.toString()]),
    groups: map.overview(lo, hi, Q.parse(query.threshold), query.mode, query).groups.map(s => [
      s.firstTime.toString(), s.lastTime.toString(), s.entryCount.toString(),
      s.distinctCount.toString(), s.maxGap.toString(),
    ]),
  };
});
const arithmetic = data.arithmetic.map(([sa, sb]) => {
  const a = Q.parse(sa), b = Q.parse(sb);
  return [a.toString(), b.toString(), a.compare(b).toString(),
    a.add(b).toString(), a.sub(b).toString(), a.mul(b).toString(), a.div(b).toString()];
});
process.stdout.write(JSON.stringify({queries, arithmetic}));
