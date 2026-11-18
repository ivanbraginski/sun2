# -*- coding: utf-8 -*-
"""
可扩展字幕抓取器：给一个合集 season_id，自动抓取全部集数字幕并转文本。
用法：
  python fetch_season.py <season_id> <bvid样例> <输出子目录名>
例：
  python fetch_season.py 4569651 BV14ZChY2EMi wangayi
说明：
  <bvid样例> 用于从 view 接口拿到 ugc_season 元数据（season 详情接口本身需登录且路径会变）。
  需提供 SESSDATA；Edge 独占 cookie 时需手动从 DevTools 复制。
"""
import json, urllib.request, urllib.parse, hashlib, time, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

SESS = os.environ.get("BILI_SESSDATA", "在此填入SESSDATA")
COOKIE = "SESSDATA=" + SESS + "; buvid3=D9D2987C-3826-0DBE-4762-0D5D08CD556D95681infoc"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://www.bilibili.com/", "Cookie": COOKIE}
MIXIN = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
BASE = os.path.dirname(os.path.abspath(__file__))

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())

def sign(p, mix):
    p = dict(p); p["wts"] = int(time.time()); p = dict(sorted(p.items()))
    q = urllib.parse.urlencode({k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()})
    p["w_rid"] = hashlib.md5((q + mix).encode()).hexdigest()
    return urllib.parse.urlencode(p)

def ts(sec):
    m, s = divmod(float(sec), 60); return "%02d:%05.2f" % (int(m), s)

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    season_id, sample_bvid, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    trans = os.path.join(BASE, "transcripts_" + outdir)
    os.makedirs(trans, exist_ok=True)

    nav = get("https://api.bilibili.com/x/web-interface/nav")
    if not nav["data"]["isLogin"]:
        print("ERROR: SESSDATA 无效，未登录"); sys.exit(2)
    w = nav["data"]["wbi_img"]
    raw = w["img_url"].rsplit("/",1)[-1].split(".")[0] + w["sub_url"].rsplit("/",1)[-1].split(".")[0]
    MIX = "".join(raw[i] for i in MIXIN)[:32]

    v = get("https://api.bilibili.com/x/web-interface/view?bvid=" + sample_bvid)
    season = v["data"].get("ugc_season")
    if not season or str(season["id"]) != str(season_id):
        print("ERROR: 样例BV不在指定合集，或 season_id 不匹配"); sys.exit(3)
    eps = []
    for sec in season["sections"]:
        for ep in sec["episodes"]:
            eps.append({"bvid": ep.get("bvid"), "cid": ep.get("cid"), "title": ep.get("title")})
    print("TASKS", len(eps), "season:", season["title"])

    def work(ep):
        bvid = ep["bvid"]; out = os.path.join(trans, bvid + ".txt")
        if os.path.exists(out) and os.path.getsize(out) > 200: return bvid,"skip",0
        try:
            r = get("https://api.bilibili.com/x/player/wbi/v2?" + sign({"bvid":bvid,"cid":ep["cid"]}, MIX))
            subs = r.get("data",{}).get("subtitle",{}).get("subtitles",[])
            if not subs: return bvid,"NO_SUB",0
            sub = next((s for s in subs if s.get("lan")=="ai-zh"), subs[0])
            url = sub["subtitle_url"]; url = "https:"+url if url.startswith("//") else url
            j = get(url)
            lines = []
            for b in j.get("body",[]):
                t = b.get("content","").replace("\\N"," ").strip()
                if t: lines.append("["+ts(b.get("from",0))+"] "+t)
            content = "\n".join(lines)
            if len(content)<100: return bvid,"SHORT",len(content)
            open(out,"w",encoding="utf-8").write(content)
            return bvid,"ok",len(content)
        except Exception as e:
            return bvid,"ERR:"+str(e)[:50],0

    ok=fail=0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs={ex.submit(work,ep):ep for ep in eps}
        for f in as_completed(futs):
            b,st,n=f.result()
            if st in ("ok","skip"): ok+=1
            else: fail+=1
            print(st,b,n,flush=True)
    # 保存任务清单供后续提取用
    json.dump([{"bvid":e["bvid"],"title":e["title"],"cid":e["cid"],
                "source":season["title"],"group":"王阿姨合集"} for e in eps],
              open(os.path.join(BASE,"season_%s_tasks.json"%outdir),"w",encoding="utf-8"),
              ensure_ascii=False,indent=2)
    print("DONE ok=%d fail=%d -> %s"%(ok,fail,trans))

if __name__ == "__main__":
    main()
