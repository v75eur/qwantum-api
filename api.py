from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests, os, dns.resolver, csv, time, random, threading, re, base64
from datetime import datetime

app = Flask(__name__)
CORS(app)

KEYS = os.environ.get('GROQ_KEYS','').split(',') or ['demo']
SITE_PASSWORD = os.environ.get('SITE_PASSWORD', 'RickRoss1994@')
GH_TOKEN = os.environ.get('GH_TOKEN','')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
LIVE_LOGS = []
LOG_LOCK = threading.Lock()

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f"[{t}] {msg}"
    print(line, flush=True)
    with LOG_LOCK:
        LIVE_LOGS.append(line)
        if len(LIVE_LOGS) > 500: LIVE_LOGS.pop(0)

GITHUB_API = "https://api.github.com"
REPO = "v75eur/qwantum"
HEADERS = {"Authorization": f"token {GH_TOKEN}"} if GH_TOKEN else {}

# Fichiers CSV
DNS_FILE = 'dns_valid.csv'
SMTP_FILE = 'smtp_verified.csv'
CONFIRMED_FILE = 'banque_verified.csv'
BRUTE_FILE = 'banque_emails.csv'

def count_csv(filename):
    try:
        with open(filename) as f: return len(f.readlines()) - 1
    except: return 0

def read_csv(filename):
    e = []
    try:
        with open(filename) as f:
            for l in f.readlines()[1:]:
                if l.strip(): e.append(l.strip())
    except: pass
    return e

def fetch_github_csv(filename):
    e = []
    try:
        url = f"https://raw.githubusercontent.com/{REPO}/main/{filename}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            for l in r.text.strip().split('\n')[1:]:
                if l.strip(): e.append(l.strip())
    except: pass
    return e

def push_to_github(filename, content):
    if not GH_TOKEN: return False
    try:
        encoded = base64.b64encode(content.encode()).decode()
        url = f"{GITHUB_API}/repos/{REPO}/contents/{filename}"
        r = requests.get(url, headers=HEADERS)
        sha = r.json().get('sha','') if r.status_code == 200 else ''
        data = {"message": f"📊 {filename}", "content": encoded}
        if sha: data["sha"] = sha
        r = requests.put(url, headers=HEADERS, json=data)
        return r.status_code in [200,201]
    except: return False

def get_github_minutes():
    try:
        r = requests.get(f"{GITHUB_API}/repos/{REPO}/actions/workflows", headers=HEADERS)
        if r.status_code == 200:
            return {"used": "~30 min/jour", "limit": "66 min/jour", "restant": "~36 min/jour"}
    except: pass
    return {"used": "?", "limit": "66 min/jour", "restant": "?"}

def dns_ok(email):
    try: dns.resolver.resolve(email.split('@')[1], 'MX'); return True
    except: return False

def scrape_npm(kw):
    found = []
    try:
        r = requests.get(f"https://registry.npmjs.org/-/v1/search?text={kw}&size=50", timeout=10)
        if r.status_code == 200:
            for obj in r.json().get("objects",[]):
                for m in obj.get("package",{}).get("maintainers",[]):
                    mail = m.get("email","")
                    if EMAIL_REGEX.search(mail):
                        em = mail.lower()
                        if em not in found:
                            if dns_ok(em): found.append(em); log(f"✅ DNS: {em}")
                            else: log(f"❌ DNS KO: {em}")
    except: pass
    return found

def scrape_github(kw):
    found = []
    if not GH_TOKEN: return found
    try:
        r = requests.get(f"{GITHUB_API}/search/code?q={kw}+@gmail.com&per_page=20", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for item in r.json().get("items",[]):
                repo = item.get("repository",{}).get("full_name","")
                path = item.get("path","")
                for br in ['main','master']:
                    try:
                        r2 = requests.get(f"https://raw.githubusercontent.com/{repo}/{br}/{path}", timeout=5)
                        if r2.status_code == 200:
                            for e in EMAIL_REGEX.findall(r2.text):
                                em = e.lower()
                                if em not in found:
                                    if dns_ok(em): found.append(em); log(f"✅ GH: {em}")
                                    else: log(f"❌ GH DNS: {em}")
                    except: pass
    except: pass
    return found

def scraper_loop():
    WORDS = ['trading','forex','crypto','investing','stocks','bitcoin','ethereum','finance','business','marketing','startup','python','javascript','react','node','developer','blockchain','defi','nft','ai','machine','data','cloud','docker','aws']
    SEEN = set(read_csv(DNS_FILE))
    log(f"🚀 SCRAPER 6h-00h | DNS: {len(SEEN)} | SMTP: {count_csv(SMTP_FILE)} | PRO: {len(fetch_github_csv(CONFIRMED_FILE))}")
    last_push = time.time()
    while True:
        h = datetime.now().hour
        if 6 <= h < 24:
            kw = random.choice(WORDS)
            log(f"🔍 {kw}")
            new = scrape_npm(kw) + scrape_github(kw)
            added = 0
            for em in new:
                if em not in SEEN:
                    SEEN.add(em); added += 1
            if added:
                with open(DNS_FILE, 'w', newline='') as f:
                    w = csv.writer(f); w.writerow(['email'])
                    for e in sorted(SEEN): w.writerow([e])
                log(f"📊 DNS +{added} | DNS: {len(SEEN)} | SMTP: {count_csv(SMTP_FILE)} | PRO: {len(fetch_github_csv(CONFIRMED_FILE))}")
            if time.time() - last_push > 3600:
                with open(DNS_FILE) as f: dns_content = f.read()
                if push_to_github(DNS_FILE, dns_content):
                    log(f"📤 Push DNS: {count_csv(DNS_FILE)} emails")
                gh_min = get_github_minutes()
                log(f"⏱️ GitHub: {gh_min['restant']} restant")
                last_push = time.time()
            time.sleep(random.randint(10, 30))
        else:
            log(f"💤 Nuit | DNS: {len(SEEN)} | SMTP: {count_csv(SMTP_FILE)} | PRO: {len(fetch_github_csv(CONFIRMED_FILE))}")
            time.sleep(60)

threading.Thread(target=scraper_loop, daemon=True).start()

@app.route('/')
def home(): return "QWANTUM API OK"

@app.route('/count-dns')
def count_dns(): return jsonify({"count": count_csv(DNS_FILE)})

@app.route('/count-smtp')
def count_smtp():
    smtp = len(fetch_github_csv(SMTP_FILE))
    return jsonify({"count": smtp})

@app.route('/count-pro')
def count_pro():
    pro = len(fetch_github_csv(CONFIRMED_FILE))
    return jsonify({"count": pro})

@app.route('/github-status')
def github_status():
    return jsonify(get_github_minutes())

@app.route('/live-logs')
def live_logs():
    def generate():
        last_idx = 0
        while True:
            with LOG_LOCK:
                if len(LIVE_LOGS) > last_idx:
                    for i in range(last_idx, len(LIVE_LOGS)):
                        yield f"data: {LIVE_LOGS[i]}\n\n"
                    last_idx = len(LIVE_LOGS)
            time.sleep(0.3)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/chat', methods=['POST'])
def chat():
    d = request.get_json()
    if not d: return jsonify({"reply":"?"})
    try:
        r = requests.post('https://api.groq.com/openai/v1/chat/completions',
            headers={'Content-Type':'application/json','Authorization':f'Bearer {KEYS[0]}'},
            json={'model':'llama-3.1-8b-instant','messages':[{'role':'system','content':'Tu es QWANTUM.'},{'role':'user','content':d['message']}],'temperature':0.8,'max_tokens':200}, timeout=15)
        return jsonify({"reply": r.json()['choices'][0]['message']['content']})
    except: return jsonify({"reply": "Désolé."})


@app.route('/push-dns')
def push_dns():
    try:
        with open(DNS_FILE) as f: content = f.read()
        if push_to_github(DNS_FILE, content):
            log(f"📤 Push manuel DNS: {count_csv(DNS_FILE)} emails")
            return jsonify({"ok": True, "count": count_csv(DNS_FILE)})
        return jsonify({"ok": False, "error": "Push failed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == '__main__': app.run(host='0.0.0.0', port=10000, threaded=True)
