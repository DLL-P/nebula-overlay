import json, re, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
t = open(sys.argv[2], encoding="utf-8").read()
js = json.dumps(d, ensure_ascii=False).replace("</", r"<\/")
open(sys.argv[3], "w", encoding="utf-8").write(t.replace("__DATA__", js))
open(sys.argv[4], "w", encoding="utf-8").write(re.findall(r"<script>(.*?)</script>", t, re.S)[-1])
