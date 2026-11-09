import io
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)

BANNERS = {
    "banner-light.svg": (
        "https://capsule-render.vercel.app/api?type=venom&height=150"
        "&color=0:F6F8FA,50:D8DEE4,100:AEB8C2"
        "&text=REITHOMATO&fontColor=1F2328&fontSize=44&fontFamily=Cinzel"
        "&fontAlignY=42&desc=UM%20REINO%20CONSTRU%C3%8DDO%20EM%20C%C3%93DIGO"
        "&descAlignY=66&descSize=10&animation=fadeIn"
    ),
    "banner-dark.svg": (
        "https://capsule-render.vercel.app/api?type=venom&height=150"
        "&color=0:0D1117,50:30363D,100:58A6FF"
        "&text=REITHOMATO&fontColor=E6EDF3&fontSize=44&fontFamily=Cinzel"
        "&fontAlignY=42&desc=UM%20REINO%20CONSTRU%C3%8DDO%20EM%20C%C3%93DIGO"
        "&descAlignY=66&descSize=10&animation=fadeIn"
    ),
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "REITHOMATO-profile/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


for name, url in BANNERS.items():
    raw = fetch(url).decode("utf-8")
    if "C\ufffdDIGO" in raw or "CONSTRU\xc3\x83O" in raw:
        raise SystemExit(f"{name}: mojibake detected")
    target = os.path.join(ASSETS, name)
    io.open(target, "w", encoding="utf-8", newline="").write(raw)
    print(f"{name}: {len(raw)} chars, accent OK={'C\u00d3DIGO' in raw}")
