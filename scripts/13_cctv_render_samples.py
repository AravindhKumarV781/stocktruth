#!/usr/bin/env python3
"""PHASE 2 | Render 4 ready-made sample CCTV clips (animated aisle scenes) plus cctv/manifest.csv.
WHEN : RUNBOOK Step P2-2, if you do not have your own clips. The zip already contains the rendered clips; run this only to
       re-create them. Needs: pip install --user -r requirements-cctv.txt
WHERE: Azure Cloud Shell, from the project folder.
USAGE: python3 scripts/13_cctv_render_samples.py
OUTPUT: cctv/videos/clip01..04.mp4 and cctv/manifest.csv
The clips are drawn animations (not real footage): a shelf unit with large product labels, a faceless silhouette shopper.
  clip01 STORE_C razor cartridges: shopper takes 1 unit and leaves            -> no sale = UNBILLED_PICK
  clip02 STORE_B: shopper takes units and puts them back                       -> nothing to report
  clip03 STORE_A atta: carried unit placed on the wrong shelf (A5-S1)          -> MISPLACED_ITEM
  clip04 STORE_C razor cartridges: shopper takes units, a sale follows         -> matched, nothing to report"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

W, H, FPS, DUR = 960, 540, 10, 14
COLORS = [(60, 120, 200), (70, 160, 90), (190, 120, 60), (160, 80, 160), (60, 160, 170), (180, 90, 90)]


def wrap(text, n=13):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur]


def draw_box(img, x, y, name, color, w=130, h=84):
    cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), (240, 240, 240), 2)
    for k, line in enumerate(wrap(name)[:3]):
        cv2.putText(img, line, (x + 6, y + 24 + 24 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA)


def lerp(a, b, u):
    u = max(0.0, min(1.0, u))
    return a + (b - a) * u


def render(path, stamp, cam, scenario, target, others, left_label, right_label):
    """target = product name acted on; others = names filling the other slots."""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    # slot origins: left unit (2 shelves x 3 slots), right unit (2 shelves x 3 slots)
    def slot(unit, row, col):
        return 50 + unit * 470 + col * 145, 120 + row * 130
    tgt_slot = slot(0, 0, 1)                       # target product's home on the left unit, top shelf
    right_slot = slot(1, 1, 1)                     # wrong-shelf destination on the right unit, bottom shelf
    basket = (0, 0)
    xs = tgt_slot[0] + 65 if scenario != "wrong" else slot(1, 1, 1)[0] + 65
    for f in range(FPS * DUR):
        t = f / FPS
        img = np.full((H, W, 3), (52, 54, 58), np.uint8)
        cv2.rectangle(img, (0, 470), (W, H), (40, 42, 44), -1)
        for unit, label in ((0, left_label), (1, right_label)):
            ux = 40 + unit * 470
            cv2.rectangle(img, (ux, 100), (ux + 440, 400), (95, 98, 105), 3)
            for row in range(2):
                cv2.line(img, (ux, 210 + row * 130), (ux + 440, 210 + row * 130), (130, 133, 140), 5)
            cv2.rectangle(img, (ux, 64), (ux + 150, 94), (230, 230, 230), -1)
            cv2.putText(img, f"SHELF {label}", (ux + 6, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2, cv2.LINE_AA)
        # products in place
        names = list(others)
        for unit in (0, 1):
            for row in range(2):
                for col in range(3):
                    s = slot(unit, row, col)
                    if (unit, row, col) == (0, 0, 1):
                        continue                   # target's home handled below
                    nm = names[(unit * 6 + row * 3 + col) % len(names)]
                    draw_box(img, s[0], s[1], nm, COLORS[(unit * 6 + row * 3 + col) % len(COLORS)])
        # timeline
        px, hand, box_at, box_vis = -90, None, tgt_slot, True
        carried = False
        if scenario in ("pick", "matched"):
            px = lerp(-90, xs, t / 3.0) if t < 8 else lerp(xs, W + 90, (t - 8) / 4.0)
            if 3 <= t < 4: hand = ("shelf", (t - 3))
            if 4 <= t < 5: hand = ("carry", (t - 4)); carried = True
            if t >= 5: carried = True
            box_vis = t < 4
            if t >= 4: box_at = None
        elif scenario == "pickback":
            px = lerp(-90, xs, t / 3.0) if t < 10 else lerp(xs, W + 90, (t - 10) / 3.0)
            if 3 <= t < 4: hand = ("shelf", t - 3)
            if 4 <= t < 5: hand = ("carry", t - 4); carried = True
            if 5 <= t < 7: carried = True
            if 7 <= t < 8: hand = ("back", t - 7); carried = True
            box_vis = not (4 <= t < 8) if t < 8 else True
        elif scenario == "wrong":
            carried = t < 6
            px = lerp(-90, xs, t / 3.0) if t < 9 else lerp(xs, W + 90, (t - 9) / 3.0)
            if 4 <= t < 6: hand = ("place", (t - 4) / 2)
            box_vis = False
        if scenario == "wrong":
            pass                                     # target's home stays empty the whole clip
        elif box_vis:
            draw_box(img, tgt_slot[0], tgt_slot[1], target, COLORS[1])
        if scenario == "wrong" or not box_vis:      # shelf-edge price tag stays when the product is gone
            cv2.rectangle(img, (tgt_slot[0], tgt_slot[1] + 62), (tgt_slot[0] + 130, tgt_slot[1] + 84), (235, 235, 235), -1)
            cv2.putText(img, target[:30], (tgt_slot[0] + 3, tgt_slot[1] + 78), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (20, 20, 20), 1, cv2.LINE_AA)
        # shopper (faceless silhouette)
        sx = int(px)
        body = (150, 120, 110)
        cv2.circle(img, (sx, 250), 26, body, -1)
        cv2.rectangle(img, (sx - 30, 276), (sx + 30, 400), body, -1)
        cv2.rectangle(img, (sx - 28, 400), (sx - 4, 500), (110, 90, 85), -1)
        cv2.rectangle(img, (sx + 4, 400), (sx + 28, 500), (110, 90, 85), -1)
        bx, by = sx + 52, 420                       # basket at the shopper's side
        cv2.rectangle(img, (bx, by), (bx + 70, by + 46), (90, 160, 210), 2)
        shoulder = (sx + 30, 290)
        hand_pos = (sx + 40, 360)
        if hand:
            kind, u = hand
            if kind == "shelf": hand_pos = (int(lerp(sx + 40, tgt_slot[0] + 60, u)), int(lerp(360, tgt_slot[1] + 40, u)))
            if kind == "carry": hand_pos = (int(lerp(tgt_slot[0] + 60, bx + 30, u)), int(lerp(tgt_slot[1] + 40, by + 20, u)))
            if kind == "back": hand_pos = (int(lerp(bx + 30, tgt_slot[0] + 60, u)), int(lerp(by + 20, tgt_slot[1] + 40, u)))
            if kind == "place": hand_pos = (int(lerp(bx + 30, right_slot[0] + 60, u)), int(lerp(by + 20, right_slot[1] + 40, u)))
            if kind in ("carry", "back", "place"):
                draw_box(img, hand_pos[0] - 65, hand_pos[1] - 100, target, COLORS[1])
        cv2.line(img, shoulder, hand_pos, body, 14)
        cv2.circle(img, hand_pos, 9, body, -1)
        if carried and not hand:
            cv2.rectangle(img, (bx + 6, by + 8), (bx + 64, by + 40), COLORS[1], -1)
        if scenario == "wrong" and t >= 6:
            draw_box(img, right_slot[0], right_slot[1], target, COLORS[1])
        if scenario == "pickback" and t >= 8:
            pass
        cv2.rectangle(img, (0, 0), (W, 34), (20, 20, 20), -1)
        ts = pd.Timestamp(stamp) + pd.Timedelta(seconds=t)
        cv2.putText(img, f"{cam}   {ts:%Y-%m-%d %H:%M:%S}   REC", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
        vw.write(img)
    vw.release()


if __name__ == "__main__":
    prod = pd.read_csv(ROOT / "data" / "products.csv").set_index("sku")
    ev = pd.read_csv(ROOT / "cctv" / "sample_events.csv")
    others = ["Sona Masoori Rice 5kg", "Protein Bar 12pk", "Basmati Rice 5kg", "Green Tea 100 bags", "Ground Coffee 500g", "Olive Oil 1L"]
    others = [prod.at[s, "name"] for s in ["SKU002", "SKU009", "SKU001", "SKU004", "SKU007", "SKU008"] if s in prod.index] or others
    vids = ROOT / "cctv" / "videos"
    vids.mkdir(parents=True, exist_ok=True)

    def first(loc, sku, action, skip=0):
        r = ev[(ev.location == loc) & (ev.sku == sku) & (ev.action == action)].sort_values("ts").iloc[skip]
        return pd.Timestamp(r.ts)

    plan = [  # clip, location, sku, scenario, event time inside clip (seconds), event timestamp, camera, left label, right label
        ("clip01", "STORE_C", "SKU011", "pick", 4.0, first("STORE_C", "SKU011", "PICK", 5), "AISLE_3_CAM", "C3-S1", "C4-S1"),
        ("clip02", "STORE_B", "SKU003", "pickback", 4.0, first("STORE_B", "SKU003", "PICK"), "AISLE_2_CAM", "B2-S1", "B3-S1"),
        ("clip03", "STORE_A", "SKU005", "wrong", 6.0, first("STORE_A", "SKU005", "PUT_BACK_WRONG_SHELF"), "AISLE_5_CAM", "A3-S2", "A5-S1"),
        ("clip04", "STORE_C", "SKU011", "matched", 4.0, first("STORE_C", "SKU011", "PICK"), "AISLE_3_CAM", "C3-S1", "C4-S1"),
    ]
    rows = []
    for clip, loc, sku, scen, at, ts, cam, ll, rl in plan:
        start = ts - pd.Timedelta(seconds=at)
        other_names = [n for n in others if n != prod.at[sku, "name"]]
        render(vids / f"{clip}.mp4", start, f"{loc} {cam}", scen, prod.at[sku, "name"], other_names, ll, rl)
        rows.append(dict(clip_id=clip, location=loc, camera=cam, start_ts=str(start), file=f"{clip}.mp4"))
        print(f"rendered {clip}.mp4 ({scen}) {loc} {sku}")
    pd.DataFrame(rows).to_csv(ROOT / "cctv" / "manifest.csv", index=False)
    print("wrote cctv/manifest.csv")
