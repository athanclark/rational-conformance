#!/usr/bin/env python3
"""Run one exact contract against independently built SQLite, JS, and pgmp."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from fixture import fixture, oracle

ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

def sqlite_adapter(data, extension):
    c = sqlite3.connect(":memory:")
    c.enable_load_extension(True)
    c.load_extension(str(extension.resolve()))
    c.enable_load_extension(False)
    c.execute("CREATE VIRTUAL TABLE points USING rational_index")
    for key, weight in data["writes"]:
        # Replacement semantics match Map.set; the SQLite index enforces unique keys.
        found = c.execute("SELECT rowid FROM points WHERE time=q(?)", (key,)).fetchone()
        if found:
            c.execute("UPDATE points SET weight=? WHERE rowid=?", (int(weight), found[0]))
        else:
            c.execute("INSERT INTO points(time,weight) VALUES(?,?)", (key, int(weight)))
    answers = []
    for q in data["queries"]:
        params = (q["lower"], q["upper"], int(q["includeLower"]), int(q["includeUpper"]))
        raw = c.execute("""SELECT time,weight FROM points
            WHERE lower=? AND upper=? AND include_lower=? AND include_upper=? ORDER BY time""", params).fetchall()
        groups = c.execute("""SELECT time,last_time,weight,distinct_count,max_gap FROM points
            WHERE lower=? AND upper=? AND include_lower=? AND include_upper=?
            AND threshold=? AND mode=? ORDER BY time""", params+(q["threshold"], q["mode"])).fetchall()
        answers.append(dict(rows=[[k, str(w)] for k,w in raw],
                            groups=[[a,b,str(n),str(k),g] for a,b,n,k,g in groups]))
    arithmetic = [list(map(str, c.execute("""SELECT q(?),q(?),q_cmp(?,?),q_add(?,?),
        q_sub(?,?),q_mul(?,?),q_div(?,?)""", (a,b)*6).fetchone())) for a,b in data["arithmetic"]]
    c.close()
    return dict(queries=answers, arithmetic=arithmetic)

def literal(value):
    return "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"

# This is deliberately a scanning reference adapter. It checks pgmp arithmetic,
# comparisons and grouping semantics, without claiming an augmented pgmp index.
PG_HELPERS = """
CREATE FUNCTION pg_temp.canonical(q mpq) RETURNS text LANGUAGE sql IMMUTABLE STRICT
AS $$ SELECT num(q)::text || '/' || den(q)::text $$;
CREATE TEMP TABLE points(time mpq PRIMARY KEY, weight bigint NOT NULL);
CREATE FUNCTION pg_temp.answer(lo mpq, hi mpq, il boolean, iu boolean, threshold mpq, mode text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE r record; rows jsonb := '[]'; groups jsonb := '[]';
    first_q mpq; last_q mpq; gap mpq := '0'; total bigint; distinct_n bigint;
BEGIN
    FOR r IN SELECT time,weight FROM points
        WHERE (lo IS NULL OR time>lo OR il AND time=lo)
          AND (hi IS NULL OR time<hi OR iu AND time=hi) ORDER BY time LOOP
        rows := rows || jsonb_build_array(jsonb_build_array(pg_temp.canonical(r.time),r.weight::text));
        IF first_q IS NOT NULL AND
            r.time - (CASE WHEN mode='neighbors' THEN last_q ELSE first_q END) < threshold THEN
            gap := greatest(gap,r.time-last_q);
            last_q := r.time; total := total+r.weight; distinct_n := distinct_n+1;
        ELSE
            IF first_q IS NOT NULL THEN
                groups := groups || jsonb_build_array(jsonb_build_array(pg_temp.canonical(first_q),
                    pg_temp.canonical(last_q),total::text,distinct_n::text,pg_temp.canonical(gap)));
            END IF;
            first_q := r.time; last_q := r.time; total := r.weight; distinct_n := 1; gap := '0';
        END IF;
    END LOOP;
    IF first_q IS NOT NULL THEN
        groups := groups || jsonb_build_array(jsonb_build_array(pg_temp.canonical(first_q),
            pg_temp.canonical(last_q),total::text,distinct_n::text,pg_temp.canonical(gap)));
    END IF;
    RETURN jsonb_build_object('rows',rows,'groups',groups);
END $$;
CREATE TEMP TABLE answers(i integer,answer jsonb);
CREATE TEMP TABLE arithmetic(i integer,answer jsonb);
"""

def postgres_adapter(data, args):
    sql = ["BEGIN;"]
    if args.pg_schema:
        # --pg-schema supports locally installed, isolated pgmp during development.
        sql.append("SET search_path=" + '"' + args.pg_schema.replace('"','""') + '"' + ",public;")
    sql.append(PG_HELPERS)
    for key, weight in data["writes"]:
        sql.append(f"INSERT INTO points VALUES({literal(key)}::mpq,{int(weight)}) "
                   "ON CONFLICT(time) DO UPDATE SET weight=excluded.weight;")
    for i,q in enumerate(data["queries"]):
        params = [literal(q["lower"])+"::mpq", literal(q["upper"])+"::mpq",
                  str(q["includeLower"]).lower(), str(q["includeUpper"]).lower(),
                  literal(q["threshold"])+"::mpq", literal(q["mode"])]
        sql.append(f"INSERT INTO answers VALUES({i},pg_temp.answer({','.join(params)}));")
    for i,(a,b) in enumerate(data["arithmetic"]):
        sql.append(f"""INSERT INTO arithmetic SELECT {i},jsonb_build_array(
            pg_temp.canonical(a),pg_temp.canonical(b),
            (CASE WHEN mpq_cmp(a,b)<0 THEN '-1' WHEN mpq_cmp(a,b)>0 THEN '1' ELSE '0' END),
            pg_temp.canonical(a+b),pg_temp.canonical(a-b),pg_temp.canonical(a*b),pg_temp.canonical(a/b))
            FROM (SELECT {literal(a)}::mpq a,{literal(b)}::mpq b) s;""")
    select = """SELECT jsonb_build_object('queries',(SELECT jsonb_agg(answer ORDER BY i) FROM answers),
        'arithmetic',(SELECT jsonb_agg(answer ORDER BY i) FROM arithmetic))"""
    with tempfile.TemporaryDirectory(prefix="rational-conformance-") as temp:
        if args.pg_data:
            # PostgreSQL's single-user backend avoids sockets; the cluster must be stopped.
            target = Path(temp)/"answer.json"
            sql.append(f"COPY ({select}) TO {literal(target)};")
            command = ["postgres","--single","-j","-D",str(args.pg_data.resolve()),"postgres"]
        else:
            sql.append(select+";")
            command = ["psql","-X","-qAt","-v","ON_ERROR_STOP=1",args.pg_dsn]
        sql.append("ROLLBACK;")
        # -j accepts multiline statements, ending input at two consecutive newlines.
        script = "\n".join(sql).replace("\n\n","\n")+"\n\n"
        result = subprocess.run(command,input=script,text=True,capture_output=True,check=True,timeout=120)
        errors = [line for line in result.stderr.splitlines()
                  if re.search(r"(?:ERROR|FATAL|DETAIL|HINT|CONTEXT):", line)]
        if errors:
            raise RuntimeError("\n".join(errors[:20]))
        return json.loads(target.read_text() if args.pg_data else result.stdout)

def check(name, actual, expected):
    if actual != expected:
        for category in expected:
            for i,(a,b) in enumerate(zip(actual.get(category, []),expected[category])):
                if a != b:
                    raise AssertionError(f"{name}: {category}[{i}] differs:\n{a}\nexpected:\n{b}")
        raise AssertionError(f"{name}: result lengths or fields differ")
    print(f"PASS {name}: {len(expected['queries'])} range/overview cases, "
          f"{len(expected['arithmetic'])} arithmetic cases")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-extension",type=Path,default=ROOT/"sqlite-rational/build/sqlite_rational.so")
    parser.add_argument("--rational-map",type=Path,action="append",metavar="JS_FILE",
                        help="Built public JS entry point; repeat to test ESM and browser bundles")
    parser.add_argument("--report",type=Path,help="Write a JSON report, including failed backend checks")
    pg = parser.add_mutually_exclusive_group()
    pg.add_argument("--pg-dsn",help="Dedicated PostgreSQL test database with pgmp already installed")
    pg.add_argument("--pg-data",type=Path,help="Stopped, disposable PostgreSQL cluster for --single")
    parser.add_argument("--pg-schema",help="Schema containing pgmp types/functions; normally public")
    parser.add_argument("--require-pgmp",action="store_true")
    args = parser.parse_args()
    if args.require_pgmp and not (args.pg_dsn or args.pg_data):
        parser.error("--require-pgmp requires --pg-dsn or --pg-data")
    entries = args.rational_map or [ROOT/"rational-map/dist/index.js"]
    data = fixture()
    expected = oracle(data)
    results = []

    def run_backend(name, adapter, source=None):
        result = dict(name=name, status="passed")
        if source is not None:
            result["source"] = str(source.resolve())
        try:
            check(name,adapter(),expected)
        except Exception as error:
            detail = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail += "\n" + (error.stderr or "")
            result.update(status="failed",error=detail)
            print(f"FAIL {name}: {detail}",file=sys.stderr)
        results.append(result)

    run_backend("SQLite",lambda: sqlite_adapter(data,args.sqlite_extension),args.sqlite_extension)
    for entry in entries:
        def js_adapter():
            result = subprocess.run(["node",str(Path(__file__).with_name("browser.mjs")),str(entry.resolve())],
                                    input=json.dumps(data),text=True,capture_output=True,check=True,timeout=120)
            return json.loads(result.stdout)
        run_backend(f"RationalMap ({entry.name}, Node runtime)",js_adapter,entry)
    if args.pg_dsn or args.pg_data:
        run_backend("PostgreSQL pgmp",lambda: postgres_adapter(data,args))
    else:
        print("SKIP PostgreSQL pgmp: supply --pg-dsn or --pg-data")
        results.append(dict(name="PostgreSQL pgmp",status="skipped"))
    failed = any(result["status"] == "failed" for result in results)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(dict(
            fixture_version=data["version"],range_overview_cases=len(expected["queries"]),
            arithmetic_cases=len(expected["arithmetic"]),
            status="failed" if failed else "passed",backends=results,
        ),indent=2)+"\n")
    return int(failed)

if __name__ == "__main__":
    sys.exit(main())
