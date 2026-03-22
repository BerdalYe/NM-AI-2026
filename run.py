import argparse
import json
from pathlib import Path
import torch
import torchvision
from PIL import Image
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Laster inn ONNX-hjernen. Ingen hacking nødvendig!
    model = YOLO("best.onnx", task="detect")
    predictions =[]

    for img_path in sorted(Path(args.input).iterdir()):
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"): 
            continue
            
        image_id = int(img_path.stem.split("_")[-1])
        orig_img = Image.open(img_path).convert("RGB")
        w_img = orig_img.width
        
        # ====================================================
        # PASS 1: SER PÅ BILDET NORMALT
        # ====================================================
        res_orig = model(orig_img, conf=0.01, verbose=False)[0]
        boxes_orig = res_orig.boxes.xyxy.cpu() if res_orig.boxes else torch.empty((0,4))
        scores_orig = res_orig.boxes.conf.cpu() if res_orig.boxes else torch.empty((0,))
        classes_orig = res_orig.boxes.cls.cpu() if res_orig.boxes else torch.empty((0,))

        # ====================================================
        # PASS 2: MANUELL TTA (SER PÅ BILDET SPEILVENDT!)
        # ====================================================
        flipped_img = orig_img.transpose(Image.FLIP_LEFT_RIGHT)
        res_flip = model(flipped_img, conf=0.01, verbose=False)[0]
        boxes_flip = res_flip.boxes.xyxy.cpu() if res_flip.boxes else torch.empty((0,4))
        scores_flip = res_flip.boxes.conf.cpu() if res_flip.boxes else torch.empty((0,))
        classes_flip = res_flip.boxes.cls.cpu() if res_flip.boxes else torch.empty((0,))

        # Siden bildet var speilvendt, må vi speilvende boks-koordinatene tilbake!
        if len(boxes_flip) > 0:
            x1 = boxes_flip[:, 0].clone()
            x2 = boxes_flip[:, 2].clone()
            boxes_flip[:, 0] = w_img - x2
            boxes_flip[:, 2] = w_img - x1

        # ====================================================
        # PASS 3: SLÅR SAMMEN HAKKAMAKKAEN (ENSEMBLE)
        # ====================================================
        all_boxes = torch.cat([boxes_orig, boxes_flip], dim=0)
        all_scores = torch.cat([scores_orig, scores_flip], dim=0)
        all_classes = torch.cat([classes_orig, classes_flip], dim=0)

        if len(all_boxes) == 0:
            continue

        # RYDDER DOBLE BOKSER MED PYTORCH SIN EGEN NMS
        keep_indices =[]
        for c in torch.unique(all_classes):
            mask = all_classes == c
            b = all_boxes[mask]
            s = all_scores[mask]
            # 45% overlapp-grense
            keep = torchvision.ops.nms(b, s, 0.45) 
            indices = torch.where(mask)[0][keep]
            keep_indices.extend(indices.tolist())

        # ====================================================
        # 4. LAGRER PERFEKSJONEN TIL JSON
        # ====================================================
        for idx in keep_indices:
            x1, y1, x2, y2 = [float(v) for v in all_boxes[idx].tolist()]
            w = x2 - x1
            h = y2 - y1
            
            predictions.append({
                "image_id": image_id,
                "category_id": int(all_classes[idx].item()),
                "bbox":[round(x1, 1), round(y1, 1), round(w, 1), round(h, 1)],
                "score": round(float(all_scores[idx].item()), 3),
            })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(predictions, f)

if __name__ == "__main__":
    main()