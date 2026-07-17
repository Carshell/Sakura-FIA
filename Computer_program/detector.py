from pathlib import Path

import cv2
from ultralytics import YOLO

MODEL_PATH = Path(__file__).parent / "best.pt"

LABELS = {
    "Pothole": "Яма",
    "object": "Об'єкт",
}

COLORS = {
    "Яма": (0, 140, 255),
    "Об'єкт": (255, 140, 0),
}


class ObjectDetector:
    def __init__(self, conf=0.4):
        self.model = YOLO(str(MODEL_PATH))
        self.conf = conf

    def detect(self, frame):
        results = self.model.predict(frame, conf=self.conf, verbose=False)
        detections = []

        for result in results:
            for box in result.boxes:
                label = result.names[int(box.cls[0])]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                obj_type = LABELS.get(label, label)
                detections.append(
                    {
                        "label": label,
                        "object_type": obj_type,
                        "confidence": conf,
                        "bbox": (x1, y1, x2, y2),
                    }
                )

        return detections

    def draw(self, frame, detections):
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = COLORS.get(det["object_type"], (255, 255, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{det['object_type']} {det['confidence']:.0%}"
            cv2.putText(
                frame,
                text,
                (x1, max(y1 - 8, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )
        return frame
