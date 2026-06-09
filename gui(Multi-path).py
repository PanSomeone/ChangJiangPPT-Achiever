
import json, os, sys, time, io, shutil, hashlib, ctypes, webbrowser, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from PIL import Image
import uv
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HERE = Path(__file__).parent
CONFIG_FILE = HERE / "config.json"

if sys.platform == "win32":
    for fn in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
               lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),
               lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try: fn(); break
        except: pass

# ===== engine =====
URLS = [("changjiang","https://changjiang.yuketang.cn"),("www","https://www.yuketang.cn")]
_base = None

class Engine:
    def __init__(self):
        self.cookies={}; self.uid=""; self.base=""; self.s=None; self.stop=False; self.pause=False; self._ck={}

    def load(self):
        if not CONFIG_FILE.exists(): return False
        try:
            d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            r = str(d.get("cookie","")).strip()
            if not r: return False
            self.cookies = self._p(r)
            u = str(d.get("uid",""))
            self.uid = u if u else self._du()
            return True
        except: return False

    def save(self, raw, uid=""):
        data = {"cookie": raw, "uid": uid if uid else self._du()}
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.cookies = self._p(raw)
        self.uid = data["uid"]

    def _p(self,s):
        d={}
        for x in s.split(";"):
            x=x.strip()
            if"="in x:k,v=x.split("=",1);d[k.strip()]=v.strip()
        return d
    def _du(self):
        for k in("university_id","uv_id"):
            v=self.cookies.get(k,"")
            if v.isdigit(): return v
        return ""

    def mk(self,cid=""):
        cs=self.cookies.get("csrftoken",""); s=requests.Session(); s.cookies.update(self.cookies)
        # 连接池优化
        adapter=HTTPAdapter(pool_connections=20,pool_maxsize=20,max_retries=Retry(total=2,backoff_factor=0.1))
        s.mount("https://",adapter); s.mount("http://",adapter)
        h={"Accept":"application/json","User-Agent":"Mozilla/5.0","X-CSRFToken":cs,"X-Client":"web","Xt-Agent":"web","classroom-id":cid,"xtbz":"ykt"}
        if self.uid: h["university-id"]=h["uv-id"]=self.uid
        s.headers.update(h); return s

    def detect(self):
        global _base
        if _base: self.base=_base; return _base
        s=self.mk()
        for _,url in URLS:
            try:
                r=s.get(f"{url}/v2/api/web/userinfo",timeout=8)
                if r.json().get("errcode")==0: _base=url;self.base=url;return url
            except: pass
        _base=URLS[0][1]; self.base=_base; return _base

    def api(self,url,prm=None):
        try: return self.s.get(url,params=prm,timeout=15).json()
        except: return{}

    def courses(self):
        d=self.api(f"{self.base}/v2/api/web/courses/list",{"identity":2})
        if not d or d.get("errcode")!=0: return[]
        r=d.get("data",{}); return r if isinstance(r,list)else r.get("list",[])

    def lessons(self,cid):
        xs=[]; p=0
        while True:
            d=self.api(f"{self.base}/v2/api/web/logs/learn/{cid}",{"actype":14,"page":p,"offset":20,"sort":-1})
            if not d or d.get("errcode")!=0: break
            xs.extend(d["data"].get("activities",[]))
            if not d["data"].get("has_more"): break
            p+=1; time.sleep(0.3)
        return xs

    def pres(self,lid):
        d=self.api(f"{self.base}/api/v3/lesson-summary/student",{"lesson_id":lid})
        if not d or d.get("code")!=0: return[]
        return d.get("data",{}).get("presentations",[])

    def slides(self,lid,pid):
        d=self.api(f"{self.base}/api/v3/lesson-summary/student/presentation",{"presentation_id":pid,"lesson_id":lid})
        if not d or d.get("code")!=0: return[]
        return [s["cover"]for s in d.get("data",{}).get("slides",[])if s.get("cover")]

    def dlimg(self, url):
        """每个线程使用独立 Session，避免线程安全问题"""
        for _ in range(3):
            try:
                # 用独立请求替代 self.s，避免多线程竞争
                r = requests.get(
                    url,
                    headers=self.s.headers if self.s else {"User-Agent": "Mozilla/5.0"},
                    cookies=self.cookies,
                    timeout=10
                )
                if r.status_code == 200:
                    return r.content
                time.sleep(0.3)
            except Exception:
                time.sleep(0.3)
        return None

    def dl_slides(self, urls, prog_cb=None, workers=8):
        """并发下载幻灯片，严格保持顺序，丢页返回 None 占位"""
        results = [None] * len(urls)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self.dlimg, u): i for i, u in enumerate(urls)}
            completed = 0
            for f in as_completed(futures):
                i = futures[f]
                completed += 1
                try:
                    results[i] = f.result()
                except Exception:
                    pass
                # 每完成3个更新一次进度
                if prog_cb and completed % 3 == 0:
                    prog_cb(completed, len(urls))
        # 返回原始顺序列表（含 None），外层决定是否过滤
        return results

    def pdf(self,imgs,path):
        ps=[]
        for b in imgs:
            if not b: continue
            try: ps.append(Image.open(io.BytesIO(b)).convert("RGB"))
            except: pass
        if not ps: return False
        ps[0].save(path,save_all=True,append_images=ps[1:],format="PDF"); return True

    @staticmethod
    def saf(s): return "".join(c if c not in r'\/:*?"<>|'else"_"for c in s).strip()

    def run(self,cid,odir,prog,log):
        self.s=self.mk(cid); d=Path(odir)/cid; d.mkdir(parents=True,exist_ok=True)
        cf=d/".dl.json"; hf_=d/".hash.json"; ck=d/".ckpt.json"
        cache={}
        if cf.exists():
            try: cache=json.loads(cf.read_text(encoding="utf-8"))
            except: pass
        start=0
        if cid in self._ck: start=self._ck[cid]
        elif ck.exists():
            try: start=json.loads(ck.read_text(encoding="utf-8")).get("i",0)
            except: pass

        ls=self.lessons(cid)
        if not ls: log("[无课时]"); return

        log("扫描课件...")
        pres=[]
        for li,l in enumerate(ls):
            lid=l.get("courseware_id",""); lt=l.get("title","?")
            for p in self.pres(lid):
                pid=p.get("id",""); pt=p.get("title","")
                if not pid: continue
                sls=self.slides(lid,pid)
                fp=hashlib.md5("|".join(sls).encode()).hexdigest()if sls else None
                nm=self.saf(pt if pt else lt)+".pdf"
                pres.append({"lid":lid,"pid":pid,"sls":sls,"fp":fp,"nm":nm})
            prog(li+1,len(ls),f"扫描 {li+1}/{len(ls)}")

        total=len(pres); s={"n":0,"d":0,"s":0,"f":0}
        hc={}
        for pid_,fp_ in self._ldh(hf_).items():
            if fp_ and pid_ in cache: hc[fp_]=(pid_,cache[pid_])

        if start>0: log(f"[从第{start+1}/{total}个继续]")
        for i in range(start,total):
            while self.pause and not self.stop: time.sleep(0.3)
            if self.stop: self._ck[cid]=i; self._svc(ck,i); return
            it=pres[i]; pid=it["pid"]; nm=it["nm"]; fp=it["fp"]; sls=it["sls"]; out=str(d/nm)

            if pid in cache:
                ex=cache[pid]
                if os.path.exists(ex)and os.path.abspath(ex)!=os.path.abspath(out): shutil.copy2(ex,out)
                s["d"]+=1; prog(i+1,total); self._svc(ck,i+1); continue
            if os.path.exists(out):
                cache[pid]=out
                if fp: self._svh(hf_,pid,fp); hc[fp]=(pid,out)
                self._sv(cf,cache); s["s"]+=1; prog(i+1,total); self._svc(ck,i+1); continue
            if fp and fp in hc:
                ep,ex=hc[fp]
                if os.path.exists(ex): shutil.copy2(ex,out); cache[pid]=ex; self._sv(cf,cache)
                s["d"]+=1; log(f"[重复] {nm}"); prog(i+1,total); self._svc(ck,i+1); continue

            log(f"[下载] {len(sls)}页 -> {nm}")
            if not sls:
                s["f"] += 1;
                prog(i + 1, total);
                self._svc(ck, i + 1);
                continue
            if self.stop:
                self._ck[cid] = i;
                self._svc(ck, i);
                return
            while self.pause and not self.stop:
                time.sleep(0.3)

            # 并发下载，带进度回调
            def _pg(cur, tot):
                prog(i + 1, total, f"{nm[:30]} {cur}/{tot}")

            raw_im = self.dl_slides(sls, prog_cb=_pg)
            # 过滤失败页，但要求成功率>80%才生成PDF
            im = [b for b in raw_im if b]
            if len(im) < len(sls) * 0.8:
                log(f"[失败] {nm} (仅下载{len(im)}/{len(sls)}页,成功率不足80%)")
                s["f"] += 1
                prog(i + 1, total)
                self._svc(ck, i + 1)
                continue

            if self.pdf(im, out):
                cache[pid] = out
                if fp:
                    self._svh(hf_, pid, fp)
                    hc[fp] = (pid, out)
                self._sv(cf, cache)
                s["n"] += 1
                log(f"[完成] {nm} ({len(im)}页)")
            else:
                s["f"] += 1
            prog(i + 1, total)
            self._svc(ck, i + 1); time.sleep(0.15)

        if ck.exists(): ck.unlink()
        self._ck.pop(cid,None)
        log(f"共{total} | 新:{s['n']} 重复:{s['d']} 跳过:{s['s']} 失败:{s['f']}")

    def _sv(self,p,d):
        try: p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
        except: pass
    def _svh(self,p,pid,fp):
        try:
            d={}
            if p.exists(): d=json.loads(p.read_text(encoding="utf-8"))
            d[pid]=fp; p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
        except: pass
    def _ldh(self,p):
        try:
            if p.exists(): return json.loads(p.read_text(encoding="utf-8"))
        except: pass
        return{}
    def _svc(self,p,i):
        try: p.write_text(json.dumps({"i":i},ensure_ascii=False),encoding="utf-8")
        except: pass

# ===== GUI =====
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("长江雨课堂PPT批量下载器")
        self.geometry("680x580"); self.resizable(False,False)
        self.configure(bg="#F5F6FA")
        self.protocol("WM_DELETE_WINDOW",self._close)
        self.eng=Engine(); self.cs=[]; self.vs={}; self._ac=None

        self._build()
        self._check_login()

    def _build(self):
        # header - 44px
        hf=tk.Frame(self,bg="#4A90D9",height=44); hf.place(x=0,y=0,relwidth=1)
        hf.pack_propagate(False)
        tk.Label(hf,text="长江雨课堂 PPT 批量下载器",font=("Microsoft YaHei UI",14,"bold"),fg="white",bg="#4A90D9").pack(pady=9)
        tk.Label(self,text="@PanSomeone  · 仅供学习使用",fg="#bbb",bg="#F5F6FA",font=("Microsoft YaHei UI",7)).place(x=10,y=565)

        # account - 56px
        af=tk.Frame(self); af.place(x=10,y=50,width=660,height=56)
        tk.Label(af,text="账号状态:",font=("Microsoft YaHei UI",9)).pack(side=tk.LEFT,padx=(0,6))
        self._st=tk.Label(af,text="检测中...",fg="gray"); self._st.pack(side=tk.LEFT)
        tk.Button(af,text="粘贴 Cookie",bg="#4A90D9",fg="white",width=10,command=lambda:self._login_paste()).pack(side=tk.RIGHT,padx=(4,0))
        tk.Button(af,text="浏览器登录",width=10,command=lambda:self._login_br()).pack(side=tk.RIGHT,padx=4)

        # separator
        tk.Frame(self,bg="#ddd",height=1).place(x=10,y=110,width=660)

        # courses label + buttons
        cb=tk.Frame(self); cb.place(x=10,y=116,width=660,height=26)
        tk.Label(cb,text="选择课程",font=("Microsoft YaHei UI",9,"bold")).pack(side=tk.LEFT)
        tk.Button(cb,text="全选",font=("Microsoft YaHei UI",8),width=4,command=lambda:self._tog(True)).pack(side=tk.RIGHT,padx=2)
        tk.Button(cb,text="取消",font=("Microsoft YaHei UI",8),width=4,command=lambda:self._tog(False)).pack(side=tk.RIGHT,padx=2)
        tk.Button(cb,text="刷新",font=("Microsoft YaHei UI",8),width=4,command=lambda:self._refresh()).pack(side=tk.RIGHT,padx=2)
        self._cnt=tk.Label(cb,text="",fg="gray",font=("Microsoft YaHei UI",8)); self._cnt.pack(side=tk.RIGHT,padx=6)

        # courses list - 200px
        cf=tk.Frame(self,bg="white",bd=1,relief="solid"); cf.place(x=10,y=145,width=660,height=200)
        cv=tk.Canvas(cf,bg="white",highlightthickness=0)
        sb=tk.Scrollbar(cf,orient=tk.VERTICAL,command=cv.yview)
        self._ci=tk.Frame(cv,bg="white")
        self._ci.bind("<Configure>",lambda e:cv.configure(scrollregion=cv.bbox("all")))
        cw=cv.create_window((0,0),window=self._ci,anchor="nw",tags="inner")
        cv.configure(yscrollcommand=sb.set); cv.bind("<Configure>",lambda e:cv.itemconfig(cw,width=e.width))
        cv.pack(side=tk.LEFT,fill=tk.BOTH,expand=True); sb.pack(side=tk.RIGHT,fill=tk.Y)
        self._bind_scroll(cv)

        # output - 36px
        of=tk.Frame(self); of.place(x=10,y=355,width=660,height=36)
        tk.Label(of,text="保存到:",font=("Microsoft YaHei UI",9)).pack(side=tk.LEFT,padx=(0,6))
        self._od=tk.StringVar(value=str(HERE/"output"))
        tk.Entry(of,textvariable=self._od,width=30).pack(side=tk.LEFT,padx=4,fill=tk.X,expand=True)
        tk.Button(of,text="浏览",font=("Microsoft YaHei UI",8),width=5,command=lambda:self._od.set(filedialog.askdirectory()or self._od.get())).pack(side=tk.RIGHT)

        # progress - 42px
        pf=tk.Frame(self); pf.place(x=10,y=398,width=660,height=42)
        self._bar=ttk.Progressbar(pf,mode="determinate"); self._bar.pack(fill=tk.X)
        self._pl=tk.Label(pf,text="就绪",fg="gray",font=("Microsoft YaHei UI",8)); self._pl.pack(fill=tk.X,pady=(1,0))

        # log - 70px
        lf=tk.Frame(self); lf.place(x=10,y=445,width=660,height=70)
        self._lt=tk.Text(lf,font=("Consolas",9),height=3,wrap=tk.WORD,state=tk.DISABLED,bg="#FAFBFC")
        self._lt.pack(fill=tk.BOTH,expand=True)

        # footer - 48px
        ff=tk.Frame(self); ff.place(x=10,y=520,width=660,height=48)
        self._db=tk.Button(ff,text="开始下载",font=("Microsoft YaHei UI",10,"bold"),bg="#27ae60",fg="white",width=12,command=lambda:self._toggle_dl())
        self._db.pack(side=tk.RIGHT,padx=(4,0))
        tk.Button(ff,text="停止",bg="#FF4D4F",fg="white",width=8,command=lambda:self._do_stop()).pack(side=tk.RIGHT,padx=4)
        tk.Label(ff,text="@PanSomeone",fg="#ccc",font=("Microsoft YaHei UI",7)).pack(side=tk.LEFT,pady=10)

    def _bind_scroll(self,cv):
        def en(e): self._ac=cv
        def lv(e): self._ac=None
        def wh(e):
            if self._ac: self._ac.yview_scroll(-1*(e.delta//120),"units")
        cv.bind("<Enter>",en); cv.bind("<Leave>",lv); self.bind_all("<MouseWheel>",wh)

    # ===== logic =====
    def _log(self,msg):
        if not msg: return
        self.after(0,lambda:self._log_(msg))
    def _log_(self,msg):
        self._lt.config(state=tk.NORMAL); self._lt.insert(tk.END,msg+"\n"); self._lt.see(tk.END); self._lt.config(state=tk.DISABLED)
    def _prog(self,cur,tot,stat=""):
        self.after(0,lambda:self._prog_(cur,tot,stat))
    def _prog_(self,cur,tot,stat=""):
        self._bar["maximum"]=tot; self._bar["value"]=cur
        p=int(cur/tot*100)if tot else 0
        self._pl.config(text=f"{cur}/{tot} ({p}%)  {stat}")

    def _check_login(self):
        if self.eng.load():
            self.eng.detect()
            self._st.config(text=f"已连接 | 学校:{self.eng.uid or'?'}",fg="green")
            self._refresh()
        else:
            self._st.config(text="未配置 Cookie",fg="orange")
            # 自动创建配置文件
            if not CONFIG_FILE.exists():
                CONFIG_FILE.write_text('{"cookie":"","uid":""}', encoding="utf-8")

    def _login_br(self):
        import subprocess
        is_frozen = getattr(sys, "frozen", False)

        if is_frozen:
            # EXE 环境：直接开浏览器，手动粘贴
            self.iconify()
            self.after(500,lambda:webbrowser.open("https://changjiang.yuketang.cn/v2/web/studentLog"))
            self.after(3000,self.deiconify)
            self._log("[已打开浏览器，登录后点「粘贴 Cookie」]")
            return

        # 开发环境：调用 login.py (Playwright 全自动)
        lp = HERE / "login.py"
        if lp.exists():
            self.iconify()
            self._log("[浏览器自动登录中，请扫码...]")
            subprocess.Popen(
                [sys.executable, str(lp)],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform=="win32" else 0
            )
            self._try_count = 0
            def check():
                if self.eng.load():
                    self.deiconify()
                    self._log("[登录成功！]")
                    self._check_login()
                elif self._try_count < 60:
                    self._try_count += 1
                    self.after(5000, check)
                else:
                    self.deiconify()
                    self._log("[超时，请手动粘贴 Cookie]")
            self.after(5000, check)
        else:
            self.iconify()
            self.after(500,lambda:webbrowser.open("https://changjiang.yuketang.cn/v2/web/studentLog"))
            self.after(3000,self.deiconify)
            self._log("[浏览器已打开，登录后点「粘贴 Cookie」]")

    def _login_paste(self):
        dlg=tk.Toplevel(self); dlg.title("粘贴 Cookie"); dlg.geometry("520x340")
        dlg.transient(self); dlg.grab_set()
        tk.Label(dlg,text="粘贴 Cookie",font=("Microsoft YaHei UI",12,"bold")).pack(pady=(12,4))
        tk.Label(dlg,text="F12 -> Application -> Cookies -> 全选复制 -> 粘贴到下方",fg="gray").pack()
        t=tk.Text(dlg,font=("Consolas",9),height=6,wrap=tk.WORD); t.pack(fill=tk.BOTH,expand=True,padx=12,pady=6)
        if CONFIG_FILE.exists():
            try:
                d = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                t.insert("1.0", d.get("cookie",""))
                uv.set(d.get("uid",""))
            except: pass
        rf=tk.Frame(dlg); rf.pack(fill=tk.X,padx=12,pady=2)
        tk.Label(rf,text="学校ID:",font=("Microsoft YaHei UI",9)).pack(side=tk.LEFT)
        uv=tk.StringVar(value=self.eng.uid or"")
        tk.Entry(rf,textvariable=uv,width=16).pack(side=tk.LEFT,padx=6)
        def sv():
            r=t.get("1.0",tk.END).strip()
            if not r: messagebox.showwarning("","请输入Cookie"); return
            self.eng.save(r,uv.get().strip()); dlg.destroy(); self._log("[Cookie已保存]"); self._check_login()
        tk.Button(dlg,text="保存",bg="#4A90D9",fg="white",width=10,command=lambda:sv()).pack(pady=10)

    def _refresh(self):
        self.cs.clear(); self.vs.clear()
        for w in self._ci.winfo_children(): w.destroy()
        if not self.eng.cookies:
            tk.Label(self._ci,text="( 请先配置 Cookie )",fg="gray").pack(pady=20); return
        self.eng.detect(); self.eng.s=self.eng.mk()
        xs=self.eng.courses()
        if not xs:
            tk.Label(self._ci,text="( 未找到课程 )",fg="red").pack(pady=20); self._cnt.config(text=""); return
        self.cs=xs
        for c in xs:
            cid=str(c.get("classroom_id","?")); nm=c.get("name",c.get("course_name","?"))
            v=tk.BooleanVar(value=False); self.vs[cid]=v
            f=tk.Frame(self._ci); f.pack(fill=tk.X,padx=2)
            tk.Checkbutton(f,text=f"  {nm}  ",variable=v,anchor=tk.W,padx=4).pack(side=tk.LEFT)
            tk.Label(f,text=cid,fg="gray").pack(side=tk.RIGHT,padx=6)
        self._cnt.config(text=f"{len(xs)}个课程")

    def _tog(self,v):
        for x in self.vs.values(): x.set(v)

    # ===== download =====
    def _toggle_dl(self):
        if self.eng.pause:
            self.eng.pause=False; self._log("[继续]"); self._btn("暂停","pause"); return
        sel=[c for c,v in self.vs.items()if v.get()]
        if not sel: messagebox.showwarning("","请选择课程"); return
        self._btn("暂停","pause"); self._log("=== 开始 ===")
        self.eng.stop=False; self.eng.pause=False; self.eng._ck.clear()
        def w():
            for c in sel:
                if self.eng.stop: break
                self._log(f"--- 课堂 {c} ---")
                self.eng.run(c,self._od.get(),self._prog,self._log)
            self.after(0,self._done)
        threading.Thread(target=w,daemon=True).start()

    def _do_pause(self):
        self.eng.pause=True; self._btn("继续","resume"); self._log("[已暂停]")

    def _btn(self,text,st):
        if st=="pause":
            self._db.config(text=text,command=lambda:self._do_pause(),state=tk.NORMAL)
        elif st=="resume":
            self._db.config(text=text,command=lambda:self._toggle_dl(),state=tk.NORMAL)
        else:
            self._db.config(text="开始下载",command=lambda:self._toggle_dl(),state=tk.NORMAL)

    def _do_stop(self):
        self.eng.stop=True; self.eng.pause=False; self._btn("开始下载","start"); self._log("[已停止]")

    def _done(self):
        self._btn("开始下载", "start");self._log("=== 完成 ===")
        messagebox.showinfo("下载完成", "所有课件已下载完毕！")

    def _close(self):
        self.eng.stop=True; self.destroy()

if __name__=="__main__":
    App().mainloop()
